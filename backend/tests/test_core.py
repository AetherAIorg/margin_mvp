from __future__ import annotations

import pytest

from app.normalizer.engine import detect_family, infer_dimensions, normalize_formula, normalize_signature
from app.parsers.dax import parse_dax
from app.parsers.python_parser import parse_python
from app.parsers.sql import parse_sql
from app.execution.finance_functions import compute_periodic_irr, compute_xirr
from datetime import date


def test_normalize_signature_xirr():
    sig = normalize_signature("=XIRR(NetCashflows, CashflowDates)")
    assert "irr" in sig


def test_detect_irr_family():
    assert detect_family("Net IRR", "=XIRR(A,B)") == "IRR"


def test_infer_dimensions_net_irr():
    dims = infer_dimensions("Fund-Level Net IRR", "XIRR(NetCashflows, CashflowDates)")
    assert dims["basis"] == "net"
    assert dims["time_basis"] == "actual_date"


def test_parse_sql_finds_irr():
    sql = "SELECT iterative_irr(monthly_cashflows) AS fund_level_net_irr FROM fund_cashflows_v2"
    results = parse_sql(sql)
    assert any("irr" in r.label.lower() for r in results)


def test_parse_dax_measure():
    dax = "[Net IRR] = XIRR(FundCashflows[Amount], FundCashflows[Date])"
    results = parse_dax(dax)
    assert len(results) == 1
    assert results[0].label == "Net IRR"


def test_parse_python_deprecated():
    from pathlib import Path
    code = Path(__file__).resolve().parents[2].joinpath("demo/investment_ops_demo/legacy_irr_calculator.py").read_text()
    results = parse_python(code)
    assert any(r.is_deprecated for r in results)


def test_compute_xirr():
    values = [-100, 30, 40, 50]
    dates = [date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1), date(2023, 1, 1)]
    irr = compute_xirr(values, dates)
    assert irr is not None
    assert -0.5 < irr < 0.5


def test_compute_periodic_irr():
    irr = compute_periodic_irr([-100, 40, 40, 40])
    assert irr is not None


def test_normalize_formula():
    norm = normalize_formula("Net IRR", "=XIRR(Net Amount, Date)")
    assert norm.metric_family == "IRR"
    assert norm.function_family == "xirr"
