import numpy as np
import pandas as pd
from scipy import stats

from alternative_signals import analysis
from alternative_signals.earnings import reported_quarter, window_return
from alternative_signals.insiders import parse_form4
from alternative_signals.quarters import qidx

FORM4 = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner><reportingOwnerId><rptOwnerCik>0001234567</rptOwnerCik></reportingOwnerId></reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>25.5</value></transactionPricePerShare></transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>500</value></transactionShares></transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>200</value></transactionShares>
        <transactionPricePerShare><value>26</value></transactionPricePerShare></transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_parse_form4_keeps_open_market_buys_and_sells():
    rows = parse_form4(FORM4)
    assert [(r["code"], r["shares"], r["price"]) for r in rows] == [("P", 1000, 25.5), ("S", 200, 26)]
    assert {r["owner"] for r in rows} == {"0001234567"}


def test_reported_quarter_matches_announcement_to_quarter_just_ended():
    # Calendar fiscal year: results on 2023-02-02 report Q4 FY2022; on 2023-04-25, Q1 FY2023.
    assert reported_quarter(pd.Timestamp("2023-02-02"), 12) == qidx(2022, 4)
    assert reported_quarter(pd.Timestamp("2023-04-25"), 12) == qidx(2023, 1)
    # Logitech (March year end): late October reports fiscal Q2 (Jul-Sep).
    assert reported_quarter(pd.Timestamp("2026-10-27"), 3) == qidx(2027, 2)
    # Two days after a quarter ends is too soon to be that quarter's results, so it's the one before.
    assert reported_quarter(pd.Timestamp("2023-04-02"), 12) == qidx(2022, 4)
    # Nothing ended 5-120 days earlier (fiscal year ends in March, so quarters end Jun/Sep/Dec/Mar).
    assert reported_quarter(pd.Timestamp("2023-02-02"), 3) == qidx(2023, 3)
    assert reported_quarter(pd.Timestamp("2023-08-30"), 6) == qidx(2023, 4)


def test_window_return_spans_day_before_to_second_day():
    close = pd.Series([100.0, 90.0, 99.0, 50.0],
                      index=pd.to_datetime(["2023-02-01", "2023-02-02", "2023-02-03", "2023-02-06"]))
    assert abs(window_return(close, pd.Timestamp("2023-02-02")) - (-0.01)) < 1e-9


def _slow_permutation_p(x, y, groups, n, seed):
    rng = np.random.default_rng(seed)
    obs = abs(stats.spearmanr(x, y).statistic)
    hits = 0
    for _ in range(n):
        xs = x.copy()
        for g in np.unique(groups):
            idx = np.flatnonzero(groups == g)
            xs[idx] = x[rng.permutation(idx)]
        hits += abs(stats.spearmanr(xs, y).statistic) >= obs - 1e-12
    return (hits + 1) / (n + 1)


def test_fast_permutation_test_agrees_with_slow_one():
    rng = np.random.default_rng(3)
    x = rng.normal(size=90)
    y = 0.25 * x + rng.normal(size=90)
    groups = np.repeat(["a", "b", "c"], 30)
    fast = analysis.permutation_p(x, y, groups, n=3000, seed=1)
    slow = _slow_permutation_p(x, y, groups, n=3000, seed=2)
    assert abs(fast - slow) < 0.01


def test_q_values_benjamini_hochberg():
    q = analysis.q_values(pd.Series([0.01, 0.04, 0.03, 0.5]))
    assert np.allclose(q.tolist(), [0.04, 0.04 * 4 / 3, 0.04 * 4 / 3, 0.5])


def test_sales_surprise_removes_persistence():
    rng = np.random.default_rng(4)
    rows = []
    for t in ("A", "B"):
        g = 0.0
        for i in range(60):
            prev, g = g, 0.6 * g + rng.normal(0, 0.05)
            rows.append({"ticker": t, "qidx": i, "rev_yoy": g, "rev_yoy_prev": prev if i else np.nan})
    p = analysis.add_sales_surprise(pd.DataFrame(rows))
    assert abs(p.attrs["growth_persistence"] - 0.6) < 0.15
    d = p.dropna(subset=["sales_surprise", "rev_yoy_prev"])
    assert abs(np.corrcoef(d["sales_surprise"], d["rev_yoy_prev"])[0, 1]) < 0.1
    assert p.loc[(p.ticker == "A") & (p.qidx == 5), "sales_surprise_next"].item() == \
        p.loc[(p.ticker == "A") & (p.qidx == 6), "sales_surprise"].item()
