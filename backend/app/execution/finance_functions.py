from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
from scipy.optimize import newton


def compute_xirr(values: list[float], dates: list[date]) -> float | None:
    if len(values) != len(dates) or len(values) < 2:
        return None
    if not (any(v > 0 for v in values) and any(v < 0 for v in values)):
        return None
    base = dates[0]
    days = [(d - base).days for d in dates]

    def npv(rate: float) -> float:
        return sum(v / ((1 + rate) ** (day / 365.0)) for v, day in zip(values, days))

    try:
        return float(newton(npv, 0.1, maxiter=100))
    except (RuntimeError, ValueError):
        return None


def compute_periodic_irr(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    if not (any(v > 0 for v in values) and any(v < 0 for v in values)):
        return None

    def npv(rate: float) -> float:
        return sum(v / ((1 + rate) ** i) for i, v in enumerate(values))

    try:
        return float(newton(npv, 0.1, maxiter=100))
    except (RuntimeError, ValueError):
        return None


def compute_moic(distributions: float, nav: float, invested: float) -> float | None:
    if invested == 0:
        return None
    return (distributions + nav) / invested


def compute_dpi(distributions: float, paid_in: float) -> float | None:
    if paid_in == 0:
        return None
    return distributions / paid_in


def compute_tvpi(distributions: float, nav: float, paid_in: float) -> float | None:
    if paid_in == 0:
        return None
    return (distributions + nav) / paid_in


def compute_rvpi(nav: float, paid_in: float) -> float | None:
    if paid_in == 0:
        return None
    return nav / paid_in


TRANSFORMATIONS: dict[str, Any] = {
    "normalize_cashflow_signs": {
        "description": "Standardize cashflow signs (contributions negative, distributions positive)",
        "input_schema": {
            "columns": ["fund_id", "cashflow_date", "cashflow_amount", "cashflow_type"],
        },
        "output_schema": {
            "columns": ["fund_id", "cashflow_date", "normalized_amount", "cashflow_type"],
        },
    },
    "map_cashflow_types": {
        "description": "Map raw cashflow types to standard categories",
        "input_schema": {"columns": ["cashflow_type"]},
        "output_schema": {"columns": ["normalized_type"]},
    },
    "filter_by_fund": {
        "description": "Filter cashflows to a specific fund",
        "input_schema": {"columns": ["fund_id"]},
        "output_schema": {"columns": ["fund_id"]},
    },
    "filter_by_deal": {
        "description": "Filter cashflows to a specific deal",
        "input_schema": {"columns": ["deal_id"]},
        "output_schema": {"columns": ["deal_id"]},
    },
    "add_terminal_nav": {
        "description": "Add latest NAV as terminal cashflow for unrealized positions",
        "input_schema": {"columns": ["fund_id", "nav_amount", "nav_date"]},
        "output_schema": {"columns": ["fund_id", "cashflow_date", "normalized_amount"]},
    },
    "convert_currency": {
        "description": "Convert amounts to fund currency using FX rates",
        "input_schema": {"columns": ["amount", "currency", "fx_rate"]},
        "output_schema": {"columns": ["amount_fund_currency"]},
    },
    "apply_fee_adjustments": {
        "description": "Apply management fee adjustments to gross cashflows",
        "input_schema": {"columns": ["gross_cashflow_amount", "fee_rate"]},
        "output_schema": {"columns": ["net_cashflow_amount"]},
    },
    "aggregate_to_fund_level": {
        "description": "Aggregate deal-level cashflows to fund level",
        "input_schema": {"columns": ["fund_id", "deal_id", "cashflow_amount"]},
        "output_schema": {"columns": ["fund_id", "cashflow_amount"]},
    },
    "aggregate_to_deal_level": {
        "description": "Aggregate cashflows to deal level",
        "input_schema": {"columns": ["deal_id", "cashflow_amount"]},
        "output_schema": {"columns": ["deal_id", "cashflow_amount"]},
    },
}

FINANCIAL_FUNCTIONS: dict[str, Any] = {
    "compute_xirr": {
        "description": "Compute XIRR using actual cashflow dates",
        "function_type": "financial_calculation",
        "input_schema": {"values": "array<float>", "dates": "array<date>"},
        "output_schema": {"irr": "float"},
    },
    "compute_periodic_irr": {
        "description": "Compute IRR assuming equal monthly periods",
        "function_type": "financial_calculation",
        "input_schema": {"values": "array<float>"},
        "output_schema": {"irr": "float"},
    },
    "compute_moic": {
        "description": "Multiple on invested capital",
        "function_type": "financial_calculation",
        "input_schema": {"distributions": "float", "nav": "float", "invested": "float"},
        "output_schema": {"moic": "float"},
    },
    "compute_dpi": {
        "description": "Distributed to paid-in capital",
        "function_type": "financial_calculation",
        "input_schema": {"distributions": "float", "paid_in": "float"},
        "output_schema": {"dpi": "float"},
    },
    "compute_tvpi": {
        "description": "Total value to paid-in capital",
        "function_type": "financial_calculation",
        "input_schema": {"distributions": "float", "nav": "float", "paid_in": "float"},
        "output_schema": {"tvpi": "float"},
    },
    "compute_rvpi": {
        "description": "Residual value to paid-in capital",
        "function_type": "financial_calculation",
        "input_schema": {"nav": "float", "paid_in": "float"},
        "output_schema": {"rvpi": "float"},
    },
}
