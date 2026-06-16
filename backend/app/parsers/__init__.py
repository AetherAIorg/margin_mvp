from __future__ import annotations

import io
import re
from dataclasses import dataclass, field


@dataclass
class RawImplementation:
    location: str
    label: str
    raw_formula: str
    owner: str | None = None
    source_refs: list[str] = field(default_factory=list)
    input_columns: list[str] = field(default_factory=list)
    referenced_functions: list[str] = field(default_factory=list)
    nearby_context: str | None = None
    is_deprecated: bool = False


def artifact_type_from_filename(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xlsm", ".xls")):
        return "excel"
    if lower.endswith(".sql"):
        return "sql"
    if lower.endswith(".dax"):
        return "dax"
    if lower.endswith((".py", ".r")):
        return "python"
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith((".md", ".txt")):
        return "docs"
    raise ValueError(f"Unsupported artifact type: {filename}")


def parse_artifact(filename: str, content: bytes) -> list[RawImplementation]:
    artifact_type = artifact_type_from_filename(filename)
    if artifact_type == "excel":
        from app.parsers.excel import parse_excel

        return parse_excel(content)
    text = content.decode("utf-8", errors="replace")
    if artifact_type == "sql":
        from app.parsers.sql import parse_sql

        return parse_sql(text)
    if artifact_type == "dax":
        from app.parsers.dax import parse_dax

        return parse_dax(text)
    if artifact_type == "python":
        from app.parsers.python_parser import parse_python

        return parse_python(text)
    if artifact_type == "csv":
        from app.parsers.csv_parser import parse_csv_definitions

        return parse_csv_definitions(text)
    return []
