"""Legacy IRR calculator - DEPRECATED.

Still referenced by reporting_job.sql and deprecated_finance_logic.sql.
Use compute_xirr from finance_functions instead.
"""

import numpy as np


def calc_monthly_irr(cashflows: list[float]) -> float:
    """Deprecated monthly IRR approximation using gross cashflows.

    Does NOT include management fees or terminal NAV.
    Uses equal monthly periods instead of actual cashflow dates.
    """
    if len(cashflows) < 2:
        return 0.0
    # Simple Newton-Raphson on equal periods
    rate = 0.1
    for _ in range(100):
        npv = sum(cf / (1 + rate) ** i for i, cf in enumerate(cashflows))
        dnpv = sum(-i * cf / (1 + rate) ** (i + 1) for i, cf in enumerate(cashflows))
        if abs(dnpv) < 1e-10:
            break
        rate -= npv / dnpv
    return rate


def compute_xirr(values: list[float], dates: list) -> float:
    """Approved XIRR implementation using actual dates and net cashflows."""
    from datetime import date
    base = dates[0]
    days = [(d - base).days if isinstance(d, date) else i * 30 for i, d in enumerate(dates)]

    def npv(r):
        return sum(v / (1 + r) ** (d / 365.0) for v, d in zip(values, days))

    rate = 0.1
    for _ in range(100):
        val = npv(rate)
        dval = sum(-d / 365.0 * v / (1 + rate) ** (d / 365.0 + 1) for v, d in zip(values, days))
        if abs(dval) < 1e-10:
            break
        rate -= val / dval
    return rate
