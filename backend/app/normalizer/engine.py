from __future__ import annotations

import re
from dataclasses import dataclass

SYNONYM_MAP = {
    "xirr": "irr",
    "mround": "round",
    "sumx": "sum",
    "iterative_irr": "periodic_irr",
    "monthly_irr": "periodic_irr",
    "calc_monthly_irr": "periodic_irr",
}

FAMILY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("IRR", ["irr", "xirr", "internal rate"]),
    ("MOIC", ["moic", "multiple on invested"]),
    ("DPI", ["dpi", "distributed to paid"]),
    ("TVPI", ["tvpi", "total value to paid"]),
    ("RVPI", ["rvpi", "residual value to paid"]),
    ("NAV", ["nav", "net asset value"]),
]


@dataclass
class NormalizedFormula:
    normalized_ast: dict
    function_family: str
    metric_family: str
    dimensions: dict
    input_signature: dict
    semantic_tags: list[str]
    signature: str


def normalize_signature(raw_formula: str) -> str:
    text = raw_formula.lower().strip()
    text = re.sub(r"^=", "", text)
    text = re.sub(r"\$?[a-z]{1,3}\$?\d+", "cell", text)
    text = re.sub(r"'[^']+'!", "", text)
    text = re.sub(r"\[[^\]]+\]", "measure", text)
    text = re.sub(r"\b\w+\.\w+\b", "tablecol", text)
    text = re.sub(r"\s+", "", text)
    for old, new in SYNONYM_MAP.items():
        text = text.replace(old, new)
    text = re.sub(r"\bxirr\b", "irr", text)
    tokens = re.findall(r"[a-z_][a-z0-9_]*|\d+\.?\d*|[+\-*/(),]", text)
    tokens.sort()
    return "|".join(tokens)


def detect_family(label: str, raw_formula: str) -> str:
    haystack = f"{label} {raw_formula}".lower()
    for family, keywords in FAMILY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return family
    return "OTHER"


def detect_function_family(raw_formula: str) -> str:
    lower = raw_formula.lower()
    if "xirr" in lower:
        return "xirr"
    if "periodic_irr" in lower or "monthly_irr" in lower or "iterative_irr" in lower:
        return "periodic_irr"
    if re.search(r"\birr\b", lower):
        return "irr"
    if "moic" in lower:
        return "moic"
    if "dpi" in lower:
        return "dpi"
    if "tvpi" in lower:
        return "tvpi"
    if "rvpi" in lower:
        return "rvpi"
    if "nav" in lower:
        return "nav"
    return "unknown"


def infer_dimensions(label: str, raw_formula: str, nearby_context: str | None = None) -> dict:
    haystack = f"{label} {raw_formula} {nearby_context or ''}".lower()
    entity = "deal" if any(k in haystack for k in ["deal", "company", "portfolio company"]) else "fund"
    basis = "net" if any(k in haystack for k in ["net", "after fee", "fee-adjusted"]) else (
        "gross" if "gross" in haystack else "unknown"
    )
    status = "realized" if "realized" in haystack else ("unrealized" if "unrealized" in haystack else "unknown")
    if "xirr" in haystack or "actual date" in haystack or "cashflow date" in haystack:
        time_basis = "actual_date"
    elif "monthly" in haystack or "periodic" in haystack:
        time_basis = "monthly"
    else:
        time_basis = "unknown"
    nav_treatment = "included" if any(k in haystack for k in ["nav", "terminal"]) else (
        "excluded" if "realized" in haystack else "unknown"
    )
    fees = "included" if basis == "net" else ("excluded" if basis == "gross" else "unknown")
    currency = "fund_currency" if "fund currency" in haystack else "unknown"
    cashflow_convention = "negative_contributions" if "contribution" in haystack else "unknown"
    return {
        "entity": entity,
        "basis": basis,
        "status": status,
        "time_basis": time_basis,
        "nav_treatment": nav_treatment,
        "fees": fees,
        "currency": currency,
        "cashflow_convention": cashflow_convention,
    }


def extract_input_signature(raw_formula: str) -> dict:
    lower = raw_formula.lower()
    values = []
    dates = []
    if "net" in lower:
        values.append("net_cashflow_amount")
    elif "gross" in lower:
        values.append("gross_cashflow_amount")
    else:
        values.append("cashflow_amount")
    if "xirr" in lower or "date" in lower:
        dates.append("cashflow_date")
    if "monthly" in lower:
        dates.append("monthly_period")
    return {"values": values, "dates": dates}


def normalize_formula(label: str, raw_formula: str, nearby_context: str | None = None) -> NormalizedFormula:
    metric_family = detect_family(label, raw_formula)
    function_family = detect_function_family(raw_formula)
    dimensions = infer_dimensions(label, raw_formula, nearby_context)
    signature = normalize_signature(raw_formula)
    tags = [metric_family.lower(), function_family]
    if dimensions["basis"] != "unknown":
        tags.append(dimensions["basis"])
    if dimensions["time_basis"] != "unknown":
        tags.append(dimensions["time_basis"])
    ast = {
        "function": function_family,
        "metric_family": metric_family,
        "raw_label": label,
        "signature": signature,
    }
    return NormalizedFormula(
        normalized_ast=ast,
        function_family=function_family,
        metric_family=metric_family,
        dimensions=dimensions,
        input_signature=extract_input_signature(raw_formula),
        semantic_tags=tags,
        signature=signature,
    )
