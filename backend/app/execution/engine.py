from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

import duckdb
import pandas as pd

from app.execution.finance_functions import compute_xirr
from app.models import Dataset, Metric, MetricRun, MetricSpec
from app.storage import download_bytes, upload_text


COLUMN_ALIASES: dict[str, list[str]] = {
    "fund_id": ["fund_id", "fund", "fundid", "fund_code"],
    "cashflow_date": ["cashflow_date", "date", "transaction_date", "cf_date"],
    "cashflow_amount": ["cashflow_amount", "amount", "net_amount", "cashflow", "cf_amount"],
    "cashflow_type": ["cashflow_type", "type", "transaction_type", "cf_type"],
    "nav_amount": ["nav_amount", "nav", "net_asset_value"],
    "nav_date": ["nav_date", "valuation_date"],
}


def auto_map_columns(detected: list[str]) -> dict[str, str]:
    lower_map = {c.lower(): c for c in detected}
    mapping: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lower_map:
                mapping[canonical] = lower_map[alias]
                break
    return mapping


def validate_required_inputs(required: dict, column_mapping: dict) -> tuple[list[str], list[str]]:
    missing_required: list[str] = []
    missing_optional: list[str] = []
    for _key, spec in required.items():
        if isinstance(spec, dict):
            cols = spec.get("columns", [])
            is_required = spec.get("required", True)
        elif isinstance(spec, list):
            cols = spec
            is_required = True
        else:
            continue
        for col in cols:
            if col not in column_mapping:
                if is_required:
                    missing_required.append(col)
                else:
                    missing_optional.append(col)
    return missing_required, missing_optional


def run_transformation_plan(df: pd.DataFrame, plan: list[str], nav_df: pd.DataFrame | None = None) -> pd.DataFrame:
    result = df.copy()
    for step in plan:
        if step == "normalize_cashflow_signs":
            if "cashflow_type" in result.columns:
                result["normalized_amount"] = result.apply(
                    lambda r: -abs(r["cashflow_amount"])
                    if str(r.get("cashflow_type", "")).lower() in {"contribution", "call", "investment"}
                    else abs(r["cashflow_amount"]),
                    axis=1,
                )
            else:
                result["normalized_amount"] = result["cashflow_amount"]
        elif step == "apply_fee_adjustments":
            if "normalized_amount" not in result.columns:
                result["normalized_amount"] = result["cashflow_amount"]
            result["net_cashflow_amount"] = result["normalized_amount"] * 0.98
        elif step == "add_terminal_nav" and nav_df is not None and not nav_df.empty:
            nav_col = "nav_amount" if "nav_amount" in nav_df.columns else nav_df.columns[-1]
            fund_col = "fund_id" if "fund_id" in nav_df.columns else nav_df.columns[0]
            date_col = "nav_date" if "nav_date" in nav_df.columns else None
            for _, nav_row in nav_df.iterrows():
                nav_value = float(nav_row[nav_col])
                terminal = {
                    "fund_id": nav_row[fund_col],
                    "cashflow_date": nav_row[date_col] if date_col else datetime.now().date(),
                    "normalized_amount": nav_value,
                    "cashflow_type": "terminal_nav",
                }
                # Terminal NAV is already a net value; populate whichever amount
                # columns exist so downstream calculations don't see NaN.
                if "net_cashflow_amount" in result.columns:
                    terminal["net_cashflow_amount"] = nav_value
                result = pd.concat([result, pd.DataFrame([terminal])], ignore_index=True)
        elif step == "aggregate_to_fund_level":
            amt_col = "net_cashflow_amount" if "net_cashflow_amount" in result.columns else "normalized_amount"
            if amt_col not in result.columns:
                amt_col = "cashflow_amount"
            result = result.groupby(["fund_id", "cashflow_date"], as_index=False)[amt_col].sum()
            result.rename(columns={amt_col: "normalized_amount"}, inplace=True)
    return result


def execute_metric_run(
    metric: Metric,
    spec: MetricSpec,
    dataset: Dataset,
    nav_dataset: Dataset | None = None,
    column_mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    content = download_bytes(dataset.storage_path)
    df = pd.read_csv(io.BytesIO(content))
    detected = list(df.columns)
    mapping = column_mapping or auto_map_columns(detected)
    df = df.rename(columns={v: k for k, v in mapping.items()})

    nav_df = None
    if nav_dataset:
        nav_content = download_bytes(nav_dataset.storage_path)
        nav_df = pd.read_csv(io.BytesIO(nav_content))
        nav_mapping = auto_map_columns(list(nav_df.columns))
        nav_df = nav_df.rename(columns={v: k for k, v in nav_mapping.items()})

    missing_required, missing_optional = validate_required_inputs(spec.required_inputs, mapping)
    warnings: list[str] = []
    errors: list[str] = []

    # NAV inputs are satisfied by a separate NAV dataset when provided.
    if nav_df is not None:
        nav_cols = set(nav_df.columns)
        missing_optional = [col for col in missing_optional if col not in nav_cols]

    if missing_required:
        errors.append(f"Missing required inputs: {', '.join(missing_required)}")
        return {"status": "failed", "errors": errors, "warnings": warnings, "results": []}

    if missing_optional:
        warnings.extend(f"Missing optional input: {col}" for col in missing_optional)

    plan = spec.transformation_plan or []
    transformed = run_transformation_plan(df, plan, nav_df)

    results: list[dict[str, Any]] = []
    date_col = "cashflow_date"
    amt_col = "net_cashflow_amount" if "net_cashflow_amount" in transformed.columns else "normalized_amount"
    if amt_col not in transformed.columns:
        amt_col = "cashflow_amount"

    calc_fn = "compute_xirr"
    if spec.calculation_function and spec.calculation_function.name:
        calc_fn = spec.calculation_function.name

    for fund_id, group in transformed.groupby("fund_id"):
        clean = group.dropna(subset=[amt_col, date_col])
        values = clean[amt_col].astype(float).tolist()
        if calc_fn == "compute_xirr":
            dates = pd.to_datetime(clean[date_col]).dt.date.tolist()
            irr = compute_xirr(values, dates)
            if irr is None:
                warnings.append(f"Fund {fund_id}: could not compute IRR (check cashflow signs)")
                continue
            results.append({"fund_id": fund_id, "net_irr": round(irr * 100, 2)})
        else:
            warnings.append(f"Fund {fund_id}: calculation function {calc_fn} not fully implemented")

    funds_missing_nav = []
    if nav_df is None and "add_terminal_nav" in plan:
        funds_missing_nav = list(transformed["fund_id"].unique())
        warnings.append(f"{len(funds_missing_nav)} funds missing NAV data")

    audit = {
        "metric_id": metric.id,
        "metric_name": metric.canonical_name,
        "metric_version": metric.version,
        "spec_id": spec.id,
        "approved_by": spec.approved_by,
        "dataset": dataset.filename,
        "column_mapping": mapping,
        "transformation_plan": plan,
        "calculation_function": calc_fn,
        "rows_processed": len(df),
        "funds_calculated": len(results),
    }

    output = io.StringIO()
    if results:
        writer = csv.DictWriter(output, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    result_path = upload_text(output.getvalue(), "results", f"{metric.id}_{dataset.id}.csv")

    return {
        "status": "completed" if results else "completed_with_warnings",
        "results": results,
        "warnings": warnings,
        "errors": errors,
        "audit_log": audit,
        "result_path": result_path,
    }
