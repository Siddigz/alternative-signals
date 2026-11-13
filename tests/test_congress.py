import numpy as np
import pandas as pd

from review_pulse import copytrade
from review_pulse.congress import parse

NEW = """ID Owner Asset Transaction Date Notification Amount Cap.
Type Date Gains >
$200?
SP Palo Alto Networks, Inc. (PANW) P 02/12/2024 02/12/2024 $500,001 -
[OP] $1,000,000
F\x00\x00\x00\x00\x00 S\x00\x00\x00\x00\x00: New
D\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00: Purchased 50 call options with a strike price of $200.
Fidelity Mid Cap Index Fund P 11/02/2022 12/05/2022 $15,001 -
(FSMDX) [OT] $50,000
F\x00\x00\x00\x00\x00 S\x00\x00\x00\x00\x00: New
SP U.S. Treasury Note due 2/28/2029 P 12/15/2025 12/16/2025 Spouse/DC Over
[GS] $1,000,000
F\x00\x00\x00\x00\x00 S\x00\x00\x00\x00\x00: New
JT Apple Inc. (AAPL) [ST] S (partial) 03/01/2024 03/02/2024 $1,001 - $15,000
F\x00\x00\x00\x00\x00 S\x00\x00\x00\x00\x00: New
"""

OLD = """ID Owner Asset Transaction Date Notification Amount
Type Date
JT Potash Corporation of Saskatchewan P 07/1/2013 10/5/2013 $1,001 - $15,000
Inc. (PoT)
FILINg STaTUS: New
SUBhoLDINg oF: Brokerage #2 USaa 8425
JT Procter & gamble Company (Pg) S 08/16/2012 09/5/2012 $1,001 - $15,000
FILINg STaTUS: New
"""


def test_parse_current_layout():
    rows = parse(NEW)
    assert [r["ticker"] for r in rows] == ["PANW", "FSMDX", None, "AAPL"]
    panw, fund, note, aapl = rows
    assert (panw["owner"], panw["asset_type"], panw["tx"], panw["amt_low"], panw["amt_high"]) == \
        ("SP", "OP", "P", 500001, 1000000)
    assert panw["tx_date"] == pd.Timestamp("2024-02-12")
    assert "call options" in panw["description"]
    assert panw["asset"] == "Palo Alto Networks, Inc. (PANW)"
    assert (fund["owner"], fund["asset_type"], fund["amt_high"]) == ("self", "OT", 50000)
    assert (note["asset_type"], note["amt_low"], note["amt_high"]) == ("GS", 1000000, None)
    assert (aapl["tx"], aapl["partial"], aapl["asset_type"]) == ("S", True, "ST")


def test_parse_old_layout_with_odd_capitals():
    rows = parse(OLD)
    assert [(r["ticker"], r["tx"], r["owner"]) for r in rows] == [("POT", "P", "JT"), ("PG", "S", "JT")]
    assert rows[0]["tx_date"] == pd.Timestamp("2013-07-01")


def _prices():
    days = pd.bdate_range("2019-01-01", "2021-12-31")
    rng = np.random.default_rng(0)
    cols = ["SPY", "QQQ", "AAA", "BBB"]
    rets = rng.normal(0.0003, 0.01, size=(len(days), len(cols)))
    return pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=days, columns=cols)


def test_picking_uses_only_finished_past_trades():
    px = _prices()
    b = pd.DataFrame({
        "member": ["Early", "Late", "Late", "Late"],
        "ticker": ["AAA", "AAA", "BBB", "AAA"],
        "filed": pd.to_datetime(["2019-03-01", "2019-12-20", "2019-12-23", "2019-12-24"]),
        "tx_date": pd.to_datetime(["2019-02-01", "2019-12-01", "2019-12-01", "2019-12-01"]),
        "option": False, "amt_low": 1001, "year": 2019,
    })
    ev = copytrade.events(b, px, horizon=21)
    # Late's trades end in January 2020, after the 2020 list is drawn up, so only Early qualifies.
    assert copytrade.pick(ev, 2020, lookback=1, top=5, min_trades=1) == ["Early"]


def test_portfolio_averages_open_positions():
    px = _prices()
    b = pd.DataFrame({"member": ["A", "B"], "ticker": ["AAA", "BBB"],
                      "filed": pd.to_datetime(["2020-03-02", "2020-03-02"]),
                      "tx_date": pd.to_datetime(["2020-02-01", "2020-02-01"]),
                      "option": False, "amt_low": 1001, "year": 2020})
    ev = copytrade.events(b, px, horizon=5)
    port = copytrade.portfolio(ev, px)
    r = px[["AAA", "BBB"]].pct_change()
    e = ev["entry"].iloc[0]
    assert len(port) == 5
    assert np.allclose(port.to_numpy(), r.iloc[e + 1:e + 6].mean(axis=1).to_numpy())
    # Holding return compounds the same daily returns.
    assert np.isclose(ev["ret"].iloc[0], (1 + r["AAA"].iloc[e + 1:e + 6]).prod() - 1)


def test_newey_west_matches_ols_coefficients():
    rng = np.random.default_rng(1)
    x = rng.normal(size=500)
    y = 0.001 + 0.8 * x + rng.normal(0, 0.5, size=500)
    X = np.column_stack([np.ones(500), x])
    coef, t = copytrade.newey_west_t(y, X, lags=5)
    assert np.allclose(coef, np.linalg.lstsq(X, y, rcond=None)[0])
    assert t[1] > 10
