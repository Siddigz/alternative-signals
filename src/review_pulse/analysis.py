"""Does a change in review tone predict results and returns?

For each company and fiscal quarter t:
  d_tone[t]      = tone[t] - tone[t-1]          (the signal, known when quarter t ends)
  growth_change  = change in year-over-year revenue growth
  abn_ret        = stock return minus SPY over a quarter

Tests, each pairing the signal with an outcome:
  same-quarter results : d_tone[t] vs growth_change[t]   (results for t are announced ~1 month after t ends)
  next-quarter results : d_tone[t] vs growth_change[t+1]
  next-quarter return  : d_tone[t] vs abn_ret[t+1]       (includes the announcement of t's results)

Pooled tests remove each company's own average (a separate baseline per company), then measure
rank correlation and an OLS slope. A permutation test (shuffling the signal within each company)
gives the chance of seeing a correlation this strong by luck.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from . import financials, prices, tone
from .config import Company

OUTCOMES = {
    "same-quarter results": ("growth_change", 0),
    "next-quarter results": ("growth_change", 1),
    "next-quarter return": ("abn_ret", 1),
}
SIGNALS = {"tone": "d_tone", "stars": "d_stars"}


def company_panel(company: Company, min_reviews: int = 30) -> pd.DataFrame:
    q = tone.quarterly(company)
    q = q[q["scored"] >= min_reviews].copy()
    q = drop_partial_quarters(q)
    fin = financials.load(company.ticker)
    close, mkt = prices.load(company.ticker), prices.load(prices.MARKET)
    qs = sorted(set(q["qidx"]) | {x + 1 for x in q["qidx"]})
    rets = prices.quarterly_returns(close, mkt, qs, company.fy_end_month)

    df = q.merge(fin[["qidx", "revenue", "net_income", "rev_yoy", "growth_change", "end", "filed"]],
                 on="qidx", how="left").merge(rets, on="qidx", how="left")
    df = df.sort_values("qidx").reset_index(drop=True)
    prev = df.set_index("qidx")
    df["d_tone"] = [df.at[i, "tone"] - prev.at[q - 1, "tone"] if (q - 1) in prev.index else np.nan
                    for i, q in enumerate(df["qidx"])]
    df["d_stars"] = [df.at[i, "stars"] - prev.at[q - 1, "stars"] if (q - 1) in prev.index else np.nan
                     for i, q in enumerate(df["qidx"])]

    # Outcomes one quarter ahead (look up by qidx so gaps don't misalign).
    fin_by_q = fin.set_index("qidx")
    ret_by_q = rets.set_index("qidx")
    df["growth_change_next"] = [fin_by_q["growth_change"].get(q + 1, np.nan) for q in df["qidx"]]
    df["abn_ret_next"] = [ret_by_q["abn_ret"].get(q + 1, np.nan) for q in df["qidx"]]
    df.insert(0, "ticker", company.ticker)
    return df


def drop_partial_quarters(q: pd.DataFrame, ratio: float = 0.5) -> pd.DataFrame:
    """Drop quarters at the end of the data whose review count falls below `ratio` x the median
    of the 4 quarters before. The dataset tails off near its cutoff, leaving partial quarters."""
    q = q.sort_values("qidx").reset_index(drop=True)
    base = q["reviews"].shift(1).rolling(4, min_periods=2).median()
    while len(q) > 2 and q["reviews"].iloc[-1] < ratio * base.iloc[len(q) - 1]:
        q, base = q.iloc[:-1], base.iloc[:-1]
    return q


def outcome_col(name: str) -> str:
    col, lead = OUTCOMES[name]
    return f"{col}_next" if lead else col


@dataclass
class Result:
    signal: str
    outcome: str
    n: int
    rho: float
    p: float
    perm_p: float
    slope: float
    slope_neg: float
    slope_pos: float


def _demean(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    out[cols] = out[cols] - out.groupby("ticker")[cols].transform("mean")
    return out


def permutation_p(x: np.ndarray, y: np.ndarray, groups: np.ndarray, n: int = 2000, seed: int = 0) -> float:
    """Two-sided p-value for Spearman rho, shuffling x within each group."""
    rng = np.random.default_rng(seed)
    obs = abs(stats.spearmanr(x, y).statistic)
    idx_by_group = [np.flatnonzero(groups == g) for g in np.unique(groups)]
    hits = 0
    for _ in range(n):
        xs = x.copy()
        for idx in idx_by_group:
            xs[idx] = x[rng.permutation(idx)]
        if abs(stats.spearmanr(xs, y).statistic) >= obs:
            hits += 1
    return (hits + 1) / (n + 1)


def test(panel: pd.DataFrame, signal: str, outcome: str) -> Result | None:
    x_col, y_col = SIGNALS[signal], outcome_col(outcome)
    d = panel[["ticker", x_col, y_col]].dropna()
    if len(d) < 8:
        return None
    d = _demean(d, [x_col, y_col])
    x, y = d[x_col].to_numpy(), d[y_col].to_numpy()
    rho, p = stats.spearmanr(x, y)
    slope = np.polyfit(x, y, 1)[0]
    # Asymmetry: separate slopes for drops and rises in tone.
    X = np.column_stack([np.minimum(x, 0), np.maximum(x, 0), np.ones_like(x)])
    (s_neg, s_pos, _), *_ = np.linalg.lstsq(X, y, rcond=None)
    return Result(signal, outcome, len(d), float(rho), float(p),
                  permutation_p(x, y, d["ticker"].to_numpy()), float(slope), float(s_neg), float(s_pos))


def run(panel: pd.DataFrame) -> pd.DataFrame:
    """Pooled and per-company results for every signal/outcome pair."""
    rows = []
    groups = [("All companies", panel)] + list(panel.groupby("ticker"))
    for name, sub in groups:
        for signal in SIGNALS:
            for outcome in OUTCOMES:
                r = test(sub, signal, outcome)
                if r:
                    rows.append({"scope": name, **r.__dict__})
    return pd.DataFrame(rows)


def verdict(results: pd.DataFrame) -> str:
    """Plain-language summary of the pooled tone tests."""
    pooled = results[(results["scope"] == "All companies") & (results["signal"] == "tone")]
    if pooled.empty:
        return "Not enough data to test yet."
    lines = []
    for r in pooled.itertuples():
        strength = abs(r.rho)
        size = "no" if strength < 0.1 else "a weak" if strength < 0.25 else "a moderate" if strength < 0.5 else "a strong"
        direction = "" if size == "no" else (" positive" if r.rho > 0 else " negative (opposite to the claim)")
        luck = ("unlikely to be luck" if r.perm_p < 0.05 else
                "could easily be luck" if r.perm_p > 0.2 else "borderline")
        lines.append(f"Tone change vs {r.outcome}: {size}{direction} link "
                     f"(rank correlation {r.rho:+.2f}, {r.n} company-quarters, "
                     f"permutation p={r.perm_p:.3f}, {luck}).")
    return "\n".join(lines)
