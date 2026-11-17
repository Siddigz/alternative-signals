"""Fiscal-quarter maths.

A fiscal year is named by the calendar year it ends in. With fy_end_month=3 (Logitech),
FY2024 runs Apr 2023 - Mar 2024 and its Q1 is Apr-Jun 2023.
"""

from datetime import date, timedelta

import pandas as pd


def fiscal_quarter(d: date, fy_end_month: int) -> tuple[int, int]:
    """Return (fiscal_year, fiscal_quarter) for a date."""
    months_in = (d.month - fy_end_month - 1) % 12  # 0 = first month of the fiscal year
    fq = months_in // 3 + 1
    fy = d.year if d.month <= fy_end_month else d.year + 1
    return fy, fq


def label(fy: int, fq: int) -> str:
    return f"FY{fy}Q{fq}"


def quarter_bounds(fy: int, fq: int, fy_end_month: int) -> tuple[date, date]:
    """First and last calendar day of a fiscal quarter."""
    # Month (1-12) and year of the quarter's last month.
    end_index = fy * 12 + (fy_end_month - 1) - 3 * (4 - fq)  # months since year 0
    end_year, end_month = divmod(end_index, 12)
    end_month += 1
    start_index = end_index - 2
    start_year, start_month = divmod(start_index, 12)
    start_month += 1
    nxt_year, nxt_month = divmod(end_index + 1, 12)
    end = date(nxt_year, nxt_month + 1, 1) - timedelta(days=1)
    return date(start_year, start_month, 1), end


def period_end_quarter(end: date, fy_end_month: int) -> tuple[int, int]:
    """Fiscal quarter for a reported period end date.

    52/53-week companies end periods on e.g. Jan 1 or Oct 1, a few days into the
    next month, so step back 10 days before mapping.
    """
    return fiscal_quarter(end - timedelta(days=10), fy_end_month)


def add_quarter_columns(df: pd.DataFrame, date_col: str, fy_end_month: int) -> pd.DataFrame:
    """Add fy, fq, quarter (label) and qidx (sortable integer) columns."""
    dates = pd.to_datetime(df[date_col])
    months_in = (dates.dt.month - fy_end_month - 1) % 12
    out = df.copy()
    out["fy"] = dates.dt.year + (dates.dt.month > fy_end_month).astype(int)
    out["fq"] = months_in // 3 + 1
    out["qidx"] = out["fy"] * 4 + out["fq"] - 1
    out["quarter"] = "FY" + out["fy"].astype(str) + "Q" + out["fq"].astype(str)
    return out


def qidx(fy: int, fq: int) -> int:
    return fy * 4 + fq - 1
