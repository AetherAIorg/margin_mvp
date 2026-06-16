from __future__ import annotations

import ast
import re

from app.parsers import RawImplementation

FINANCE_FN_PATTERN = re.compile(
    r"\b(compute_xirr|compute_periodic_irr|calc_\w*irr\w*|compute_moic|compute_dpi|compute_tvpi|compute_rvpi|xirr|irr)\b",
    re.I,
)


def _extract_from_function(node: ast.FunctionDef, source: str, module_deprecated: bool = False) -> RawImplementation | None:
    body_text = ast.get_source_segment(source, node) or ""
    if not FINANCE_FN_PATTERN.search(body_text) and not FINANCE_FN_PATTERN.search(node.name):
        return None
    doc = ast.get_docstring(node) or ""
    deprecated = module_deprecated or bool(re.search(r"\b(legacy|deprecated|old)\b", node.name + doc, re.I))
    return_raw = ""
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and child.value:
            return_raw = ast.get_source_segment(source, child.value) or ""
            break
    return RawImplementation(
        location=f"function: {node.name}",
        label=node.name.replace("_", " ").title(),
        raw_formula=body_text[:2000],
        nearby_context=doc[:500] if doc else None,
        referenced_functions=sorted(set(FINANCE_FN_PATTERN.findall(body_text))),
        is_deprecated=deprecated,
    )


def parse_python(text: str) -> list[RawImplementation]:
    results: list[RawImplementation] = []
    module_deprecated = bool(re.search(r"\b(legacy|deprecated)\b", text[:500], re.I))
    try:
        tree = ast.parse(text)
    except SyntaxError:
        for match in FINANCE_FN_PATTERN.finditer(text):
            results.append(
                RawImplementation(
                    location=f"match: {match.group(1)}",
                    label=match.group(1).replace("_", " ").title(),
                    raw_formula=text[max(0, match.start() - 50) : match.end() + 200],
                    referenced_functions=[match.group(1)],
                    is_deprecated=bool(re.search(r"\b(legacy|deprecated|old)\b", text, re.I)),
                )
            )
        return results

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            impl = _extract_from_function(node, text, module_deprecated)
            if impl:
                results.append(impl)
    return results
