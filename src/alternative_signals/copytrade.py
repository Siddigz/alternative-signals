"""Backtest: copy House members' disclosed stock purchases, picking whom to copy only from past results.

The claim being tested (a popular guide on Reddit): the best-performing members beat the market even
when you only buy once their trade is disclosed. Picking "the best" with hindsight guarantees a winning
list, so here each year's list is chosen only from trades that were disclosed *and* whose holding period
had ended before that year began. Then that list's purchases disclosed during the year are copied.

Copying rule: buy at the close of the first trading day after the report was filed, hold for a fixed
number of trading days. The portfolio holds every open copied position in equal weight each day
(a "calendar-time" portfolio, so overlapping trades aren't double counted).

Results are measured against SPY and against QQQ (Nasdaq-100), since many members' winning trades were
big tech stocks: beating QQQ is the bar for showing skill rather than a tech tilt. t-statistics use
Newey-West standard errors because daily portfolio returns overlap.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import congress

STOCK_TYPES = {"ST", None}  # older reports have no asset-type tag; a ticker means a listed security


def buys(trades: pd.DataFrame, options: bool = True) -> pd.DataFrame:
    """Purchases of listed stocks (and, if `options`, call options, copied as the underlying stock)."""
    t = trades[(trades["tx"] == "P") & trades["ticker"].notna() & trades["filed"].notna()].copy()
    t["asset_type"] = t["asset_type"].where(t["asset_type"].notna(), None)
    is_stock = t["asset_type"].isin(["ST"]) | t["asset_type"].isna()
    is_call = (t["asset_type"] == "OP") & ~t["description"].str.contains(r"\bput", case=False, na=False)
    t = t[is_stock | (is_call if options else False)]
    t["option"] = t["asset_type"] == "OP"
    t["ticker"] = t["ticker"].map(congress.yahoo_symbol)
    # Several lots of one stock in one report count as one copied trade.
    return (t.sort_values("tx_date")
             .groupby(["member", "ticker", "filed"], as_index=False)
             .agg(tx_date=("tx_date", "first"), option=("option", "max"), amt_low=("amt_low", "sum"),
                  year=("year", "first")))


def events(b: pd.DataFrame, px: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Entry/exit positions and returns for each copied trade (dropped if prices are missing)."""
    days = px.index
    entry = days.searchsorted(b["filed"].values, side="right")      # first trading day after filing
    entry_tx = days.searchsorted(b["tx_date"].values, side="left")  # first trading day on/after the trade
    entry_tx = np.minimum(entry_tx, entry)  # a few trade dates are typos later than the filing
    out = b.copy()
    out["entry"], out["entry_tx"] = entry, entry_tx
    out["exit"] = entry + horizon
    out = out[(out["exit"] < len(days)) & out["ticker"].isin(px.columns)]
    cols = {c: i for i, c in enumerate(px.columns)}
    a = px.to_numpy()
    ci = out["ticker"].map(cols).to_numpy()
    e, x, et = out["entry"].to_numpy(), out["exit"].to_numpy(), out["entry_tx"].to_numpy()
    spy, qqq = cols["SPY"], cols["QQQ"]
    p0, p1, p0tx = a[e, ci], a[x, ci], a[et, ci]
    out["ret"] = p1 / p0 - 1
    out["ret_spy"] = a[x, spy] / a[e, spy] - 1
    out["ret_qqq"] = a[x, qqq] / a[e, qqq] - 1
    out["ret_from_trade"] = p1 / p0tx - 1        # if you could have bought on the trade date
    out["spy_from_trade"] = a[x, spy] / a[et, spy] - 1
    out["entry_date"], out["exit_date"] = days[e], days[x]
    out = out[np.isfinite(out["ret"]) & (p0 > 0)]
    return out.reset_index(drop=True)


def pick(ev: pd.DataFrame, year: int, lookback: int, top: int, min_trades: int, bottom: bool = False) -> list[str]:
    """Members with the best (or worst) average return vs SPY on trades disclosed in the previous
    `lookback` years whose holding period ended before `year` began."""
    start, cutoff = pd.Timestamp(year - lookback, 1, 1), pd.Timestamp(year, 1, 1)
    past = ev[(ev["filed"] >= start) & (ev["exit_date"] < cutoff)]
    score = (past.assign(x=past["ret"] - past["ret_spy"]).groupby("member")["x"]
             .agg(["mean", "size"]).query("size >= @min_trades")["mean"])
    score = score.sort_values(ascending=bottom)
    return list(score.index[:top])


def ranking(ev: pd.DataFrame, year: int, s: "Setup") -> pd.DataFrame:
    """The members the setup copies in `year`, with their past average return vs SPY and trade count."""
    start, cutoff = pd.Timestamp(year - s.lookback, 1, 1), pd.Timestamp(year, 1, 1)
    past = ev[(ev["filed"] >= start) & (ev["exit_date"] < cutoff)]
    score = (past.assign(x=past["ret"] - past["ret_spy"]).groupby("member")["x"].agg(["mean", "size"])
             .query("size >= @s.min_trades").sort_values("mean", ascending=False).head(s.top))
    return score.rename(columns={"mean": "past_vs_spy", "size": "past_trades"})


def portfolio(ev: pd.DataFrame, px: pd.DataFrame) -> pd.Series:
    """Daily return of an equal-weighted portfolio of all open copied positions."""
    rets = px.pct_change().to_numpy()
    cols = {c: i for i, c in enumerate(px.columns)}
    total, count = np.zeros(len(px)), np.zeros(len(px))
    for c, e, x in zip(ev["ticker"].map(cols), ev["entry"], ev["exit"]):
        r = rets[e + 1:x + 1, c]
        ok = np.isfinite(r)
        total[e + 1:x + 1][ok] += r[ok]
        count[e + 1:x + 1][ok] += 1
    s = pd.Series(np.where(count > 0, total / np.maximum(count, 1), np.nan), index=px.index)
    return s.dropna()


def newey_west_t(y: np.ndarray, X: np.ndarray, lags: int = 10) -> tuple[np.ndarray, np.ndarray]:
    """OLS coefficients and Newey-West t-statistics."""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    u = y - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X)
    Xu = X * u[:, None]
    S = Xu.T @ Xu
    for l in range(1, lags + 1):
        w = 1 - l / (lags + 1)
        G = Xu[l:].T @ Xu[:-l]
        S += w * (G + G.T)
    se = np.sqrt(np.diag(XtX_inv @ S @ XtX_inv))
    return beta, beta / se


def alpha(port: pd.Series, bench: pd.Series) -> dict:
    """Yearly alpha and beta of the portfolio against one benchmark (daily regression)."""
    d = pd.concat([port, bench], axis=1, keys=["p", "b"]).dropna()
    if len(d) < 60:
        return {"days": len(d), "alpha": np.nan, "t": np.nan, "beta": np.nan, "excess": np.nan}
    X = np.column_stack([np.ones(len(d)), d["b"].to_numpy()])
    coef, t = newey_west_t(d["p"].to_numpy(), X)
    return {"days": len(d), "alpha": coef[0] * 252, "t": t[0], "beta": coef[1],
            "excess": (d["p"] - d["b"]).mean() * 252}


@dataclass
class Setup:
    horizon: int = 126       # trading days held (about 6 months)
    lookback: int = 2        # years of past trades used to rank members
    top: int = 30
    min_trades: int = 5
    options: bool = True     # copy call-option buys as the stock
    first_year: int = 2016
    last_year: int | None = None
    halal: bool = False      # shares only, in permissible industries (see congress.HARAM_SIC)


def copied(ev: pd.DataFrame, s: Setup, group: str = "top") -> pd.DataFrame:
    """The trades a follower would have copied, year by year."""
    last = s.last_year or int(ev["filed"].dt.year.max())
    parts = []
    for y in range(s.first_year, last + 1):
        this = ev[ev["filed"].dt.year == y]
        if group == "all":
            parts.append(this)
            continue
        names = pick(ev, y, s.lookback, s.top, s.min_trades, bottom=(group == "bottom"))
        parts.append(this[this["member"].isin(names)].assign(picked_year=y))
    return pd.concat(parts, ignore_index=True) if parts else ev.iloc[0:0]


def summary(ev_all: pd.DataFrame, px: pd.DataFrame, s: Setup, group: str = "top") -> dict:
    ev = ev_all if s.options and not s.halal else ev_all[~ev_all["option"]]
    if s.halal:
        sic = congress.fetch_sic(sorted(ev["ticker"].unique()))
        ok = set(sic.loc[sic["sic"].map(congress.permissible_sic), "ticker"])
        ev = ev[ev["ticker"].isin(ok)]
    c = copied(ev, s, group)
    if c.empty:
        return {"group": group, "trades": 0}
    port = portfolio(c, px)
    bench = px[["SPY", "QQQ"]].pct_change()
    spy, qqq = alpha(port, bench["SPY"]), alpha(port, bench["QQQ"])
    return {
        "group": group, "trades": len(c), "members": c["member"].nunique(),
        "per_trade_vs_spy": float((c["ret"] - c["ret_spy"]).mean()),
        "per_trade_vs_qqq": float((c["ret"] - c["ret_qqq"]).mean()),
        "beat_spy_share": float((c["ret"] > c["ret_spy"]).mean()),
        "from_trade_date_vs_spy": float((c["ret_from_trade"] - c["spy_from_trade"]).mean()),
        "alpha_spy": spy["alpha"], "t_spy": spy["t"], "beta_spy": spy["beta"],
        "alpha_qqq": qqq["alpha"], "t_qqq": qqq["t"], "beta_qqq": qqq["beta"],
        "days": spy["days"],
    }


def run(setups: dict[str, Setup] | None = None) -> pd.DataFrame:
    trades = congress.load_trades()
    px = congress.load_prices()
    b = buys(trades, options=True)
    setups = setups or variants()
    rows, cache = [], {}
    for name, s in setups.items():
        if s.horizon not in cache:
            cache[s.horizon] = events(b, px, s.horizon)
        ev = cache[s.horizon]
        if s.last_year:
            ev = ev[ev["filed"].dt.year <= s.last_year]
        for g in ("top", "all", "bottom"):
            rows.append({"setup": name, **summary(ev, px, s, g)})
    return pd.DataFrame(rows)


def variants() -> dict[str, Setup]:
    return {
        "main: top 30, 2-year record, hold 6 months": Setup(),
        "hold 1 month": Setup(horizon=21),
        "hold 3 months": Setup(horizon=63),
        "top 10": Setup(top=10),
        "1-year record": Setup(lookback=1),
        "3-year record": Setup(lookback=3),
        "shares only (no options)": Setup(options=False),
        "years 2016-2019": Setup(last_year=2019),
        "years 2020 on": Setup(first_year=2020),
        "halal: shares only, permissible industries": Setup(halal=True),
    }
