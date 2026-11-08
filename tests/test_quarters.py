from datetime import date

import pandas as pd

from review_pulse.quarters import add_quarter_columns, fiscal_quarter, period_end_quarter, quarter_bounds


def test_march_year_end_logitech():
    # Logitech FY2024 = Apr 2023 - Mar 2024
    assert fiscal_quarter(date(2023, 4, 1), 3) == (2024, 1)
    assert fiscal_quarter(date(2023, 6, 30), 3) == (2024, 1)
    assert fiscal_quarter(date(2023, 12, 31), 3) == (2024, 3)
    assert fiscal_quarter(date(2024, 3, 31), 3) == (2024, 4)


def test_february_year_end_helen_of_troy():
    # FY2024 = Mar 2023 - Feb 2024
    assert fiscal_quarter(date(2023, 3, 1), 2) == (2024, 1)
    assert fiscal_quarter(date(2023, 11, 30), 2) == (2024, 3)
    assert fiscal_quarter(date(2024, 2, 29), 2) == (2024, 4)


def test_december_year_end():
    assert fiscal_quarter(date(2022, 1, 15), 12) == (2022, 1)
    assert fiscal_quarter(date(2022, 12, 31), 12) == (2022, 4)


def test_bounds_round_trip():
    for m in (2, 3, 9, 12):
        for fy in (2019, 2023):
            for fq in (1, 2, 3, 4):
                s, e = quarter_bounds(fy, fq, m)
                assert fiscal_quarter(s, m) == (fy, fq)
                assert fiscal_quarter(e, m) == (fy, fq)
                assert 89 <= (e - s).days + 1 <= 92


def test_52_53_week_period_end():
    # YETI-style year ending Jan 1 belongs to the previous December's Q4.
    assert period_end_quarter(date(2022, 1, 1), 12) == (2021, 4)
    # Sonos-style quarter ending Oct 1 is fiscal Q4 (year ends September).
    assert period_end_quarter(date(2022, 10, 1), 9) == (2022, 4)


def test_vectorised_matches_scalar():
    dates = pd.date_range("2019-01-01", "2021-12-31", freq="17D")
    df = add_quarter_columns(pd.DataFrame({"d": dates}), "d", 3)
    for d, fy, fq in zip(dates, df["fy"], df["fq"]):
        assert fiscal_quarter(d.date(), 3) == (fy, fq)
