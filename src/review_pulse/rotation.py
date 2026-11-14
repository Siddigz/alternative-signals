"""Sector rotation backtest: each month, hold the top-ranked sectors by a signal; compare with holding all.

Rules
- At the end of month t, compute each sector's signal from returns up to and including month t only.
- Hold the top `k` sectors in equal weight during month t+1. Trading costs `cost` per unit of turnover
  (0.10% by default: buying 1/3 of the portfolio and selling another 1/3 costs 0.067%).
- Benchmark: all sectors in equal weight (what rotation is trying to beat), and the market.

Signals
- momentum: return over the past `lookback` months, skipping the most recent `skip` month(s), the
  classic industry-momentum signal (Moskowitz & Grinblatt 1999).
- reversal: minus last month's return (last month's losers bounce).
- low volatility: minus the standard deviation of the past `lookback` monthly returns.

Testing
Settings (lookback, skip, k) are chosen on 1927-1989 only, then the chosen setting is run unchanged on
1990-today and on the sector ETFs (1999-today). Alpha is the yearly return left after allowing for how much
the portfolio moves with the equal-weight benchmark; t-statistics use Newey-West standard errors.
"""

from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

from .copytrade import newey_west_t

IN_SAMPLE = ("1927-01-01", "1989-12-31")
OUT_SAMPLE = ("1990-01-01", None)


@dataclass(frozen=True)
class Rule:
    signal: str = "momentum"   # momentum | reversal | low volatility
    lookback: int = 12
    skip: int = 1
    k: int = 3
    cost: float = 0.001

    @property
    def label(self) -> str:
        if self.signal == "momentum":
            return f"momentum {self.lookback}m" + (f", skip {self.skip}" if self.skip else "") + f", top {self.k}"
        if self.signal == "low volatility":
            return f"low volatility {self.lookback}m, top {self.k}"
        return f"reversal, top {self.k}"


def signal(rets: pd.DataFrame, rule: Rule) -> pd.DataFrame:
    """Signal known at the end of each month (higher = more attractive). NaN until enough history."""
    if rule.signal == "momentum":
        growth = np.log1p(rets)
        s = growth.shift(rule.skip).rolling(rule.lookback, min_periods=rule.lookback).sum()
    elif rule.signal == "reversal":
        s = -rets
    elif rule.signal == "low volatility":
        s = -rets.rolling(rule.lookback, min_periods=rule.lookback).std()
    else:
        raise ValueError(rule.signal)
    return s.where(rets.notna())


def weights(sig: pd.DataFrame, k: int) -> pd.DataFrame:
    """Equal weights on the top k sectors each month (ties broken by column order)."""
    rank = sig.rank(axis=1, ascending=False, method="first")
    w = (rank <= k).astype(float)
    n = w.sum(axis=1)
    return w.div(n.where(n > 0), axis=0).fillna(0.0)


def backtest(rets: pd.DataFrame, rule: Rule) -> pd.DataFrame:
    """Monthly portfolio return (after costs), turnover and the equal-weight benchmark."""
    w = weights(signal(rets, rule), rule.k).shift(1).fillna(0.0)  # chosen at the end of t, held in t+1
    held = w.sum(axis=1) > 0
    gross = (w * rets.fillna(0.0)).sum(axis=1)
    turnover = w.diff().abs().sum(axis=1)  # the first purchase counts as buying from cash
    turnover.iloc[0] = w.iloc[0].abs().sum()
    out = pd.DataFrame({
        "ret": gross - rule.cost * turnover,
        "turnover": turnover,
        "ew": rets.mean(axis=1),  # all sectors that exist that month, equal weight
    })[held]
    return out


def drawdown(r: pd.Series) -> float:
    wealth = (1 + r).cumprod()
    return float((wealth / wealth.cummax() - 1).min())


def stats(bt: pd.DataFrame, rf: pd.Series, market: pd.Series | None = None,
          start: str | None = None, end: str | None = None) -> dict:
    d = bt.loc[start:end].copy()
    d["rf"] = rf.reindex(d.index).ffill().fillna(0.0)
    if market is not None:
        d["mkt"] = market.reindex(d.index)
    if len(d) < 24:
        return {"months": len(d)}
    ex, ew_ex = d["ret"] - d["rf"], d["ew"] - d["rf"]
    coef, t = newey_west_t(ex.to_numpy(), np.column_stack([np.ones(len(d)), ew_ex.to_numpy()]), lags=6)
    active = d["ret"] - d["ew"]
    _, t_active = newey_west_t(active.to_numpy(), np.ones((len(d), 1)), lags=6)
    years = len(d) / 12
    out = {
        "months": len(d), "start": d.index[0].strftime("%Y-%m"), "end": d.index[-1].strftime("%Y-%m"),
        "cagr": float((1 + d["ret"]).prod() ** (1 / years) - 1),
        "ew_cagr": float((1 + d["ew"]).prod() ** (1 / years) - 1),
        "vol": float(d["ret"].std() * np.sqrt(12)),
        "sharpe": float(ex.mean() / ex.std() * np.sqrt(12)),
        "ew_sharpe": float(ew_ex.mean() / ew_ex.std() * np.sqrt(12)),
        "active": float(active.mean() * 12), "t_active": float(t_active[0]),
        "alpha": float(coef[0] * 12), "t_alpha": float(t[0]), "beta": float(coef[1]),
        "max_dd": drawdown(d["ret"]), "ew_max_dd": drawdown(d["ew"]),
        "turnover": float(d["turnover"].mean() * 12),
        "beat_ew_months": float((active > 0).mean()),
    }
    if market is not None and d["mkt"].notna().sum() > 24:
        m = d.dropna(subset=["mkt"])
        y = (1 + m["mkt"]).prod() ** (12 / len(m)) - 1
        out["mkt_cagr"] = float(y)
    return out


def grid() -> list[Rule]:
    rules = [Rule("momentum", lb, sk, k) for lb, sk, k in product((3, 6, 9, 12), (0, 1), (2, 3, 4))]
    rules += [Rule("reversal", 1, 0, k) for k in (2, 3, 4)]
    rules += [Rule("low volatility", lb, 0, k) for lb in (12, 36) for k in (2, 3, 4)]
    return rules


def choose(rets: pd.DataFrame, rf: pd.Series, rules: list[Rule]) -> pd.DataFrame:
    """Every rule's in-sample and out-of-sample results; `chosen` marks each signal's best in-sample rule."""
    rows = []
    for r in rules:
        bt = backtest(rets, r)
        ins = stats(bt, rf, start=IN_SAMPLE[0], end=IN_SAMPLE[1])
        oos = stats(bt, rf, start=OUT_SAMPLE[0], end=OUT_SAMPLE[1])
        rows.append({"rule": r, "label": r.label, "signal": r.signal,
                     **{f"in_{k}": v for k, v in ins.items()}, **{f"out_{k}": v for k, v in oos.items()}})
    df = pd.DataFrame(rows)
    best = df.loc[df.groupby("signal")["in_t_alpha"].idxmax()]
    df["chosen"] = df.index.isin(best.index)
    return df


def holm(p: pd.Series) -> pd.Series:
    """Holm-adjusted p-values (family-wise), for testing a few chosen rules at once."""
    order = p.sort_values().index
    m = len(p)
    adj, running = {}, 0.0
    for i, idx in enumerate(order):
        running = max(running, min(1.0, (m - i) * p[idx]))
        adj[idx] = running
    return pd.Series(adj).reindex(p.index)


def p_from_t(t: float) -> float:
    from scipy import stats as st

    return float(2 * st.norm.sf(abs(t)))


def by_decade(bt: pd.DataFrame) -> pd.DataFrame:
    d = bt.assign(active=bt["ret"] - bt["ew"])
    g = d.groupby((d.index.year // 10) * 10)["active"]
    return pd.DataFrame({"active": g.mean() * 12, "beat_share": g.apply(lambda x: (x > 0).mean()), "months": g.size()})

