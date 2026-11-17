import numpy as np
import pandas as pd

from alternative_signals import cycle, macro

FRED = """observation_date,UNRATE
2020-01-01,3.5
2020-02-01,.
2020-03-01,4.4
"""


def test_parse_fred_uses_month_ends_and_skips_missing():
    s = macro.parse_fred(FRED)
    assert list(s.index) == [pd.Timestamp("2020-01-31"), pd.Timestamp("2020-03-31")]
    assert s.iloc[-1] == 4.4


def test_known_shifts_to_publication_month():
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2020-01-31", "2020-02-29"]))
    k = macro.known(s, 1)
    assert list(k.index) == [pd.Timestamp("2020-02-29"), pd.Timestamp("2020-03-31")]


def _rets(n=200, seed=0, cols=("NoDur", "Hlth", "Durbl", "BusEq")):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("1960-01-31", periods=n, freq="ME")
    return pd.DataFrame(rng.normal(0.01, 0.05, size=(n, len(cols))), index=idx, columns=list(cols))


def test_switch_holds_defensives_only_while_warning_is_on():
    r = _rets(4)
    warn = pd.Series([True, False, np.nan, True], index=r.index)
    w = cycle.switch_weights(r, warn, "industries")
    assert w.iloc[0][["NoDur", "Hlth"]].tolist() == [0.5, 0.5] and w.iloc[0][["Durbl", "BusEq"]].sum() == 0
    assert w.iloc[1][["Durbl", "BusEq"]].tolist() == [0.5, 0.5]
    assert w.iloc[2].sum() == 0  # indicator unknown: stay out


def test_forecast_uses_only_past_returns():
    r = _rets()
    rng = np.random.default_rng(1)
    ind = pd.DataFrame(rng.normal(size=(len(r), 4)), index=r.index,
                       columns=["term", "inflation", "production", "unemp_gap"])
    t = r.index[150]
    w1 = cycle.forecast_weights(r, ind, k=2, min_months=60)
    r2 = r.copy()
    r2.loc[r.index[151]:] = rng.normal(0, 0.5, size=r2.loc[r.index[151]:].shape)  # change month t+1 onward
    w2 = cycle.forecast_weights(r2, ind, k=2, min_months=60)
    assert w1.loc[t].equals(w2.loc[t])
    assert np.isclose(w1.loc[t].sum(), 1.0)
