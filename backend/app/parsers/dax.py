from __future__ import annotations

import re

from app.parsers import RawImplementation

DAX_MEASURE_PATTERN = re.compile(
    r"(?P<name>\[[^\]]+\]|\w+)\s*=\s*(?P<expr>[^\n;]+)",
    re.IGNORECASE,
)

FINANCE_KEYWORDS = re.compile(r"\b(XIRR|IRR|SUM|DIVIDE|CALCULATE|AVERAGE|MOIC|DPI|TVPI|RVPI|NAV)\b", re.I)


def _extract_dax_refs(expr: str) -> list[str]:
    refs = re.findall(r"\b'([^']+)'\[[^\]]+\]|\[([^\]]+)\]", expr)
    return sorted({r for pair in refs for r in pair if r})


def _extract_functions(expr: str) -> list[str]:
    return sorted(set(re.findall(r"\b([A-Z][A-Z0-9_]*)\s*\(", expr)))


def parse_dax(text: str) -> list[RawImplementation]:
    results: list[RawImplementation] = []
    for match in DAX_MEASURE_PATTERN.finditer(text):
        name = match.group("name").strip("[]")
        expr = match.group("expr").strip()
        if not FINANCE_KEYWORDS.search(expr):
            continue
        label = name.replace("_", " ")
        deprecated = bool(re.search(r"\b(legacy|deprecated|old)\b", name, re.I))
        results.append(
            RawImplementation(
                location=f"measure [{name}]",
                label=label,
                raw_formula=expr,
                source_refs=_extract_dax_refs(expr),
                referenced_functions=_extract_functions(expr),
                is_deprecated=deprecated,
            )
        )
    return results
