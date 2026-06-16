from __future__ import annotations

import csv
import io

from app.parsers import RawImplementation


def parse_csv_definitions(text: str) -> list[RawImplementation]:
    results: list[RawImplementation] = []
    reader = csv.DictReader(io.StringIO(text))
    for row_no, row in enumerate(reader, start=2):
        name = row.get("metric_name") or row.get("name") or row.get("Metric")
        formula = row.get("formula") or row.get("Formula") or row.get("definition")
        if not name or not formula:
            continue
        owner = row.get("owner") or row.get("Owner")
        deprecated = (row.get("status") or "").lower() in {"deprecated", "legacy"}
        results.append(
            RawImplementation(
                location=f"row {row_no}",
                label=name.strip(),
                raw_formula=formula.strip(),
                owner=owner.strip() if owner else None,
                nearby_context=row.get("description") or row.get("Description"),
                is_deprecated=deprecated,
            )
        )
    return results


def sniff_csv_columns(content: bytes) -> tuple[list[str], int]:
    text = content.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return [], 0
    return rows[0], max(0, len(rows) - 1)
