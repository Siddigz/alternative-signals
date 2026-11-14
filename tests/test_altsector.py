import numpy as np
import pandas as pd

from review_pulse import altsector

SIC = """ 1 NoDur  Consumer Nondurables -- Food, Tobacco
          0100-0999
          2000-2399

 6 BusEq  Business Equipment -- Computers, Software
          3570-3579
          7370-7379

12 Other  Other -- Mines, Constr, BldMt, Trans, Hotels, Bus Serv, Entertainment
"""


def test_sic_ranges_and_industry_lookup():
    r = altsector.parse_sic_ranges(SIC)
    assert r == [("NoDur", 100, 999), ("NoDur", 2000, 2399), ("BusEq", 3570, 3579), ("BusEq", 7370, 7379)]
    assert altsector.industry(7372, r) == "BusEq"
    assert altsector.industry(2086, r) == "NoDur"
    assert altsector.industry(1000, r) == "Other"
    assert altsector.industry(np.nan, r) is None


def _trades():
    return pd.DataFrame({
        "filed": pd.to_datetime(["2020-01-10", "2020-01-20", "2020-01-25", "2020-02-03", "2020-02-28"]),
        "owner": ["a", "a", "b", "c", "d"],
        "issuer_cik": [1, 1, 2, 1, 2],
        "code": ["P", "P", "S", "S", "P"],
    })


def test_monthly_counts_count_each_person_company_pair_once_by_filing_month():
    sector = pd.Series({1: "BusEq", 2: "NoDur"})
    b, s = altsector.monthly_counts(_trades(), "owner", "issuer_cik", sector, "code", "P", "S")
    jan, feb = pd.Timestamp("2020-01-31"), pd.Timestamp("2020-02-29")
    assert b.loc[jan, "BusEq"] == 1          # owner a bought twice in January: one pair
    assert s.loc[jan, "NoDur"] == 1
    assert s.loc[feb, "BusEq"] == 1 and b.loc[feb, "NoDur"] == 1


def test_net_ratio_window_and_no_trades():
    idx = pd.date_range("2020-01-31", periods=4, freq="ME")
    b = pd.DataFrame({"X": [1, 0, 0, 3], "Y": [0, 0, 0, 0]}, index=idx)
    s = pd.DataFrame({"X": [1, 2, 0, 1], "Y": [0, 0, 0, 0]}, index=idx)
    r = altsector.net_ratio(b, s, window=2, relative=False)
    assert np.isnan(r.iloc[0]["X"])                       # not enough history yet
    assert np.isclose(r.iloc[1]["X"], (1 - 3) / 4)        # Jan+Feb
    assert np.isclose(r.iloc[3]["X"], (3 - 1) / 4)        # Mar+Apr
    assert r.iloc[3]["Y"] == 0                            # nobody traded: neutral
