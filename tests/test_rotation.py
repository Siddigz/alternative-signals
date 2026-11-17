import numpy as np
import pandas as pd

from alternative_signals import rotation
from alternative_signals.rotation import Rule
from alternative_signals.sectors import parse_french

FRENCH = """This file was created using the 202609 CRSP database.
Missing data are indicated by -99.99 or -999.

  Average Value Weighted Returns -- Monthly
,NoDur,Durbl,Enrgy
192607,   1.44,  15.58,  -1.14
192608,   3.99, -99.99,   3.43

  Average Equal Weighted Returns -- Monthly
,NoDur,Durbl,Enrgy
192607,   9.99,   9.99,   9.99
"""


def test_parse_french_reads_first_table_only():
    df = parse_french(FRENCH)
    assert list(df.columns) == ["NoDur", "Durbl", "Enrgy"]
    assert list(df.index) == [pd.Timestamp("1926-07-31"), pd.Timestamp("1926-08-31")]
    assert np.isclose(df.loc["1926-07-31", "Durbl"], 0.1558)
    assert np.isnan(df.loc["1926-08-31", "Durbl"])


def _rets(n=30, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2000-01-31", periods=n, freq="ME")
    return pd.DataFrame(rng.normal(0.01, 0.05, size=(n, 4)), index=idx, columns=list("ABCD"))


def test_momentum_skips_the_latest_month_and_uses_no_future_data():
    r = _rets()
    s = rotation.signal(r, Rule("momentum", lookback=3, skip=1))
    t = r.index[10]
    expected = np.log1p(r.loc[r.index[7]:r.index[9]]).sum()  # months t-3..t-1
    assert np.allclose(s.loc[t], expected)
    # Changing a later month must not change the signal at t.
    r2 = r.copy()
    r2.iloc[11:] = 0.5
    assert np.allclose(rotation.signal(r2, Rule("momentum", 3, 1)).loc[t], s.loc[t])


def test_backtest_holds_last_months_winners_and_charges_costs():
    idx = pd.date_range("2000-01-31", periods=3, freq="ME")
    r = pd.DataFrame({"A": [0.10, 0.02, 0.01], "B": [-0.10, 0.04, 0.03], "C": [0.00, 0.06, -0.02]}, index=idx)
    rule = Rule("momentum", lookback=1, skip=0, k=1, cost=0.01)
    bt = rotation.backtest(r, rule)
    # End of Jan: A was best, so February holds A (bought from cash: turnover 1).
    assert np.isclose(bt.loc[idx[1], "ret"], 0.02 - 0.01 * 1)
    # End of Feb: C was best, so March switches A -> C (turnover 2).
    assert np.isclose(bt.loc[idx[2], "ret"], -0.02 - 0.01 * 2)
    assert np.isclose(bt.loc[idx[2], "ew"], np.mean([0.01, 0.03, -0.02]))


def test_reversal_buys_last_months_loser():
    idx = pd.date_range("2000-01-31", periods=2, freq="ME")
    r = pd.DataFrame({"A": [0.10, 0.0], "B": [-0.10, 0.05]}, index=idx)
    bt = rotation.backtest(r, Rule("reversal", 1, 0, k=1, cost=0.0))
    assert np.isclose(bt.loc[idx[1], "ret"], 0.05)


def test_holm_adjustment():
    p = pd.Series({"a": 0.01, "b": 0.04, "c": 0.03})
    adj = rotation.holm(p)
    assert np.allclose(adj[["a", "c", "b"]].to_numpy(), [0.03, 0.06, 0.06])
