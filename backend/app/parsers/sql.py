from __future__ import annotations

import re

from app.parsers import RawImplementation

SQL_ALIAS_PATTERN = re.compile(
    r"(?P<expr>[\w\s\(\)\+\-\*/,\.'\[\]]+?)\s+AS\s+(?P<alias>[a-zA-Z_][\w]*)",
    re.IGNORECASE,
)

FINANCE_KEYWORDS = re.compile(
    r"\b(SUM|AVG|COUNT|XIRR|IRR|COALESCE|CASE|ROUND|DIVIDE|MOIC|DPI|TVPI|RVPI|NAV)\b",
    re.I,
)


def _extract_sql_refs(expr: str) -> list[str]:
    tables = re.findall(r"\b(?:FROM|JOIN)\s+([\w\.]+)", expr, re.I)
    columns = re.findall(r"\b([\w]+\.[\w]+)\b", expr)
    return sorted({*tables, *columns})


def _extract_functions(expr: str) -> list[str]:
    return sorted(set(re.findall(r"\b([a-zA-Z_][\w]*)\s*\(", expr)))


def parse_sql(text: str) -> list[RawImplementation]:
    results: list[RawImplementation] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in SQL_ALIAS_PATTERN.finditer(line):
            expr = match.group("expr").strip()
            alias = match.group("alias")
            if not FINANCE_KEYWORDS.search(expr):
                continue
            label = alias.replace("_", " ").title()
            deprecated = bool(re.search(r"\b(legacy|deprecated|old)\b", alias, re.I))
            results.append(
                RawImplementation(
                    location=f"line {line_no}: {alias}",
                    label=label,
                    raw_formula=expr,
                    source_refs=_extract_sql_refs(text),
                    referenced_functions=_extract_functions(expr),
                    is_deprecated=deprecated,
                )
            )

    # Also capture standalone function calls
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in re.finditer(r"\b(iterative_irr|compute_xirr|monthly_irr|calc_\w+)\s*\(", line, re.I):
            fn = match.group(1)
            label = fn.replace("_", " ").title()
            deprecated = bool(re.search(r"\b(legacy|deprecated|old)\b", fn, re.I))
            results.append(
                RawImplementation(
                    location=f"line {line_no}: {fn}",
                    label=label,
                    raw_formula=line.strip(),
                    source_refs=_extract_sql_refs(text),
                    referenced_functions=[fn],
                    is_deprecated=deprecated,
                )
            )
    return results
