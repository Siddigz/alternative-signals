"""Business-cycle sector rotation: move to defensive sectors when the economy looks to be slowing.

Strategies (all decided at month end with indicators known by then, held the next month):
- defensive switch: when a slowdown warning is on, hold the defensive sectors (consumer staples, health care,
  utilities, telecom); otherwise hold the cyclical ones. Warnings: inverted yield curve, rising unemployment
  (Sahm rule), falling industrial production, or any of them.
- momentum + switch: step 1's momentum rule, but picking only among defensive sectors while a warning is on.
- macro forecast: for each sector, a regression of next month's return (relative to all sectors) on the four
  indicators, fitted only on data before that month (expanding window, at least 10 years); hold the top 3.

As in step 1, each family's best version is chosen on 1955-1989 and tested unchanged on 1990-today.
"""

import numpy as np
import pandas as pd

from . import macro, rotation
from .rotation import Rule

IN_SAMPLE = ("1955-01-01", "1989-12-31")
OUT_SAMPLE = ("1990-01-01", None)

DEFENSIVE = {"industries": ["NoDur", "Hlth", "Utils", "Telcm"], "etfs": ["XLP", "XLV", "XLU"]}
CYCLICAL = {"industries": ["Durbl", "Manuf", "Enrgy", "Chems", "BusEq", "Shops", "Money", "Other"],
            "etfs": ["XLY", "XLI", "XLK", "XLB", "XLE", "XLF", "XLC"]}
WARNINGS = ["inverted curve", "rising unemployment", "falling production", "any warning"]


def warning(reg: pd.DataFrame, name: str) -> pd.Series:
    if name == "any warning":
        w = reg[["inverted curve", "rising unemployment", "falling production"]].any(axis=1)
    else:
        w = reg[name].astype(bool)
    return w.where(reg.notna().all(axis=1))


def _equal(rets: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    w = pd.DataFrame(0.0, index=rets.index, columns=rets.columns)
    avail = rets[[c for c in cols if c in rets.columns]].notna()
    w[avail.columns] = avail.astype(float)
    return w.div(w.sum(axis=1).where(lambda n: n > 0), axis=0).fillna(0.0)


def switch_weights(rets: pd.DataFrame, warn: pd.Series, kind: str) -> pd.DataFrame:
    warn = warn.reindex(rets.index)
    d, c = _equal(rets, DEFENSIVE[kind]), _equal(rets, CYCLICAL[kind])
    on = warn.fillna(False).astype(bool)
    w = c.mul(~on, axis=0) + d.mul(on, axis=0)
    return w.where(warn.notna(), 0.0)


def momentum_switch_weights(rets: pd.DataFrame, warn: pd.Series, kind: str, rule: Rule = Rule()) -> pd.DataFrame:
    sig = rotation.signal(rets, rule)
    warn = warn.reindex(rets.index)
    defensive = [c for c in DEFENSIVE[kind] if c in rets.columns]
    only_def = sig.copy()
    only_def[[c for c in rets.columns if c not in defensive]] = np.nan
    on = warn.fillna(False).astype(bool)
    k_def = min(rule.k, len(defensive))
    w = rotation.weights(sig, rule.k).mul(~on, axis=0) + rotation.weights(only_def, k_def).mul(on, axis=0)
    return w.where(warn.notna(), 0.0)


def forecast_weights(rets: pd.DataFrame, ind: pd.DataFrame, k: int = 3, min_months: int = 120) -> pd.DataFrame:
    """Expanding-window regression per sector of next month's relative return on the indicators."""
    X = ind[["term", "inflation", "production", "unemp_gap"]].reindex(rets.index)
    rel_next = rets.sub(rets.mean(axis=1), axis=0).shift(-1)  # return in t+1, relative to all sectors
    preds = pd.DataFrame(np.nan, index=rets.index, columns=rets.columns)
    ok_rows = X.notna().all(axis=1)
    dates = rets.index[ok_rows]
    for i, t in enumerate(dates):
        past = dates[:i]                       # rows whose t+1 return is known by the end of t
        if len(past) < min_months:
            continue
        Xp = np.column_stack([np.ones(len(past)), X.loc[past].to_numpy()])
        xt = np.concatenate([[1.0], X.loc[t].to_numpy()])
        for col in rets.columns:
            y = rel_next.loc[past, col].to_numpy()
            keep = np.isfinite(y)
            if keep.sum() < min_months:
                continue
            b, *_ = np.linalg.lstsq(Xp[keep], y[keep], rcond=None)
            preds.loc[t, col] = xt @ b
    return rotation.weights(preds.where(rets.notna()), k)


def strategies(rets: pd.DataFrame, kind: str, ind: pd.DataFrame | None = None) -> dict[str, pd.DataFrame]:
    """Weights for every strategy version, keyed by label."""
    ind = macro.indicators() if ind is None else ind
    reg = macro.regimes(ind)
    out = {}
    for name in WARNINGS:
        out[f"defensive switch: {name}"] = switch_weights(rets, warning(reg, name), kind)
    for name in WARNINGS:
        out[f"momentum + switch: {name}"] = momentum_switch_weights(rets, warning(reg, name), kind)
    out["macro forecast, top 3"] = forecast_weights(rets, ind, 3)
    return out


def family(label: str) -> str:
    return label.split(":")[0].split(",")[0]


def evaluate(rets: pd.DataFrame, rf: pd.Series, kind: str = "industries", ind: pd.DataFrame | None = None,
             start: str = IN_SAMPLE[0]) -> pd.DataFrame:
    """In- and out-of-sample results for every version; `chosen` marks each family's best in-sample version."""
    rets = rets.loc[start:]
    rows = []
    for label, w in strategies(rets, kind, ind).items():
        bt = rotation.backtest_weights(rets, w)
        ins = rotation.stats(bt, rf, start=IN_SAMPLE[0], end=IN_SAMPLE[1])
        oos = rotation.stats(bt, rf, start=OUT_SAMPLE[0], end=OUT_SAMPLE[1])
        rows.append({"label": label, "family": family(label),
                     **{f"in_{k}": v for k, v in ins.items()}, **{f"out_{k}": v for k, v in oos.items()}})
    df = pd.DataFrame(rows)
    best = df.loc[df.groupby("family")["in_t_alpha"].idxmax()]
    df["chosen"] = df.index.isin(best.index)
    return df


def time_in_warning(ind: pd.DataFrame) -> pd.Series:
    reg = macro.regimes(ind)
    return pd.Series({n: float(warning(reg, n).dropna().mean()) for n in WARNINGS})


def sector_by_regime(rets: pd.DataFrame, warn: pd.Series, start: str, end: str | None) -> pd.DataFrame:
    """Each sector's average yearly return relative to all sectors, next month, when the warning is on vs off."""
    rel_next = rets.sub(rets.mean(axis=1), axis=0).shift(-1).loc[start:end]
    w = warn.reindex(rel_next.index)
    return pd.DataFrame({"warning on": rel_next[w == True].mean() * 12,  # noqa: E712
                         "warning off": rel_next[w == False].mean() * 12})  # noqa: E712
