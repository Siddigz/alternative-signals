"""Do the signals predict results and returns?

Signals, each known by the end of fiscal quarter t:
  tone          d_tone      = review tone[t] - tone[t-1]            (Amazon reviews, to 2023)
  stars         d_stars     = star rating[t] - stars[t-1]           (baseline for tone)
  wikipedia     wiki_yoy    = log Wikipedia views vs a year earlier
  filing words  filing_chg  = negative+uncertain word rate in filings vs a year earlier

Outcomes:
  same-quarter results : growth_change[t]   (results for t are announced ~1 month after t ends)
  next-quarter results : growth_change[t+1]
  next-quarter return  : abn_ret[t+1]       (stock minus SPY; includes the announcement of t's results)

Each signal has an expected sign: +1 if a higher value should mean better outcomes. "Aligned" rank
correlation = sign x correlation, so positive always means "in the direction the idea predicts".
Pooled tests remove each company's own average first. A permutation test (shuffling the signal
within each company) gives the chance of seeing a link this strong by luck.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from . import filings, financials, prices, tone, wiki
from .config import Company
from .quarters import fiscal_quarter, qidx

OUTCOMES = {
    "same-quarter results": "growth_change",
    "next-quarter results": "growth_change_next",
    "next-quarter return": "abn_ret_next",
}
SIGNALS = {  # name: (column, expected sign)
    "tone": ("d_tone", 1),
    "stars": ("d_stars", 1),
    "wikipedia": ("wiki_yoy", 1),
    "filing words": ("filing_chg", -1),
}


def drop_partial_quarters(q: pd.DataFrame, ratio: float = 0.5) -> pd.DataFrame:
    """Drop quarters at the end of the data whose review count falls below `ratio` x the median
    of the 4 quarters before. The dataset tails off near its cutoff, leaving partial quarters."""
    q = q.sort_values("qidx").reset_index(drop=True)
    base = q["reviews"].shift(1).rolling(4, min_periods=2).median()
    while len(q) > 2 and q["reviews"].iloc[-1] < ratio * base.iloc[len(q) - 1]:
        q, base = q.iloc[:-1], base.iloc[:-1]
    return q


def _diff(df: pd.DataFrame, col: str) -> list[float]:
    by_q = df.set_index("qidx")[col]
    return [by_q[q] - by_q[q - 1] if (q - 1) in by_q.index else np.nan for q in df["qidx"]]


def review_signals(company: Company, min_reviews: int) -> pd.DataFrame:
    try:
        q = tone.quarterly(company)
    except SystemExit:
        return pd.DataFrame(columns=["qidx", "tone", "stars", "reviews", "scored", "d_tone", "d_stars"])
    q = drop_partial_quarters(q[q["scored"] >= min_reviews].copy())
    q["d_tone"], q["d_stars"] = _diff(q, "tone"), _diff(q, "stars")
    return q.drop(columns=["quarter"])


def company_panel(company: Company, start: str, min_reviews: int = 30) -> pd.DataFrame:
    """One row per fiscal quarter with financial results from `start` onward."""
    fin = financials.load(company.ticker)
    first = qidx(*fiscal_quarter(pd.Timestamp(start).date(), company.fy_end_month))
    df = fin[fin["qidx"] >= first][["qidx", "quarter", "end", "revenue", "net_income",
                                    "rev_yoy", "growth_change"]].copy()
    close, mkt = prices.load(company.ticker), prices.load(prices.MARKET)
    rets = prices.quarterly_returns(close, mkt, sorted(set(df["qidx"]) | {q + 1 for q in df["qidx"]}),
                                    company.fy_end_month)
    for part in (review_signals(company, min_reviews), wiki.quarterly(company), filings.quarterly(company)):
        df = df.merge(part, on="qidx", how="left")
    df = df.merge(rets, on="qidx", how="left").sort_values("qidx").reset_index(drop=True)

    # Outcomes one quarter ahead (looked up by qidx so gaps don't misalign).
    g = fin.set_index("qidx")["growth_change"]
    r = rets.set_index("qidx")["abn_ret"]
    df["growth_change_next"] = [g.get(q + 1, np.nan) for q in df["qidx"]]
    df["abn_ret_next"] = [r.get(q + 1, np.nan) for q in df["qidx"]]
    df.insert(0, "ticker", company.ticker)
    num = df.columns.drop(["ticker", "quarter", "end"])
    df[num] = df[num].apply(pd.to_numeric, errors="coerce")
    return df


@dataclass
class Result:
    signal: str
    outcome: str
    n: int
    rho: float      # aligned: positive = in the predicted direction
    perm_p: float
    slope_neg: float  # aligned slope when the signal turns bad
    slope_pos: float  # aligned slope when the signal turns good


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
    x_col, sign = SIGNALS[signal]
    y_col = OUTCOMES[outcome]
    if x_col not in panel or y_col not in panel:
        return None
    d = panel[["ticker", x_col, y_col]].dropna()
    if len(d) < 8:
        return None
    d[[x_col, y_col]] -= d.groupby("ticker")[[x_col, y_col]].transform("mean")
    x, y = sign * d[x_col].to_numpy(float), d[y_col].to_numpy(float)
    if np.std(x) == 0 or np.std(y) == 0:
        return None
    rho = stats.spearmanr(x, y).statistic
    # Asymmetry: separate slopes for the signal turning bad and turning good.
    X = np.column_stack([np.minimum(x, 0), np.maximum(x, 0), np.ones_like(x)])
    (s_neg, s_pos, _), *_ = np.linalg.lstsq(X, y, rcond=None)
    return Result(signal, outcome, len(d), float(rho),
                  permutation_p(x, y, d["ticker"].to_numpy()), float(s_neg), float(s_pos))


def run(panel: pd.DataFrame) -> pd.DataFrame:
    """Pooled and per-company results for every signal/outcome pair."""
    rows = []
    for name, sub in [("All companies", panel)] + list(panel.groupby("ticker")):
        for signal in SIGNALS:
            for outcome in OUTCOMES:
                r = test(sub, signal, outcome)
                if r:
                    rows.append({"scope": name, **r.__dict__})
    return pd.DataFrame(rows)


def describe(rho: float, perm_p: float) -> str:
    strength = abs(rho)
    size = "no" if strength < 0.1 else "a weak" if strength < 0.25 else "a moderate" if strength < 0.5 else "a strong"
    direction = "" if size == "no" else (" link in the predicted direction" if rho > 0
                                         else " link in the OPPOSITE direction")
    luck = ("unlikely to be luck" if perm_p < 0.05 else
            "could easily be luck" if perm_p > 0.2 else "borderline")
    return f"{size}{direction or ' link'} ({luck})"


def verdict(results: pd.DataFrame) -> str:
    """Plain-language summary of the pooled tests, one line per signal and outcome."""
    pooled = results[results["scope"] == "All companies"]
    if pooled.empty:
        return "Not enough data to test yet."
    return "\n".join(
        f"{r.signal.capitalize()} vs {r.outcome}: {describe(r.rho, r.perm_p)}. "
        f"Correlation {r.rho:+.2f}, {r.n} company-quarters, luck p={r.perm_p:.3f}."
        for r in pooled.itertuples())
