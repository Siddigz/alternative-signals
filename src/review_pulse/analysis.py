"""Do the signals predict results and returns?

Signals, each known by the end of fiscal quarter t:
  tone            d_tone      = review tone[t] - tone[t-1]                 (Amazon reviews, to 2023)
  stars           d_stars     = star rating[t] - stars[t-1]                (baseline for tone)
  wikipedia       wiki_yoy    = log Wikipedia views vs a year earlier
  google search   trends_yoy  = log Google search interest vs a year earlier
  filing words    filing_chg  = negative+uncertain word rate in filings vs a year earlier
  insider buying  insider_npr = (insiders buying - selling) / (buying + selling), Form 4s filed in t
  short interest  short_dtc   = days to cover at the quarter's last FINRA report

Outcomes:
  sales surprise         : sales_surprise[t]  year-over-year sales growth for t, minus what the previous
                           quarter's growth predicted (results for t are announced ~1 month after t ends)
  next sales surprise    : sales_surprise[t+1]
  earnings-day move      : earn_ret[t]  stock minus SPY around the announcement of t's results
  next-quarter return    : abn_ret[t+1] stock minus SPY over quarter t+1

Each signal has an expected sign: +1 if a higher value should mean better outcomes. "Aligned" rank
correlation = sign x correlation, so positive always means "in the direction the idea predicts".
Pooled tests remove each company's own average first. A permutation test (shuffling the signal
within each company) gives the chance of seeing a link this strong by luck, and a q-value adjusts
that for the number of tests run (Benjamini-Hochberg).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from . import earnings, filings, financials, insiders, prices, short_interest, tone, trends, wiki
from .config import Company
from .quarters import fiscal_quarter, qidx

OUTCOMES = {
    "sales surprise": "sales_surprise",
    "next sales surprise": "sales_surprise_next",
    "earnings-day move": "earn_ret",
    "next-quarter return": "abn_ret_next",
}
SIGNALS = {  # name: (column, expected sign)
    "tone": ("d_tone", 1),
    "stars": ("d_stars", 1),
    "wikipedia": ("wiki_yoy", 1),
    "google search": ("trends_yoy", 1),
    "filing words": ("filing_chg", -1),
    "insider buying": ("insider_npr", 1),
    "short interest": ("short_dtc", -1),
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
    df = fin[fin["qidx"] >= first][["qidx", "quarter", "end", "revenue", "net_income", "rev_yoy"]].copy()
    qs = sorted(set(df["qidx"]) | {q + 1 for q in df["qidx"]})
    try:
        close, mkt = prices.load(company.ticker), prices.load(prices.MARKET)
        rets = prices.quarterly_returns(close, mkt, qs, company.fy_end_month)
        earn = earnings.quarterly(company, close, mkt)
    except SystemExit:  # e.g. delisted, no free price history: test results only
        print(f"{company.ticker}: no prices, skipping return tests")
        rets = pd.DataFrame({"qidx": qs, "ret": np.nan, "mkt_ret": np.nan, "abn_ret": np.nan})
        earn = pd.DataFrame(columns=["qidx", "earn_date", "earn_ret"])
    parts = (review_signals(company, min_reviews), wiki.quarterly(company), trends.quarterly(company),
             filings.quarterly(company), insiders.quarterly(company), short_interest.quarterly(company), earn)
    for part in parts:
        df = df.merge(part, on="qidx", how="left")
    df = df.merge(rets, on="qidx", how="left").sort_values("qidx").reset_index(drop=True)

    # Values from neighbouring quarters, looked up by qidx so gaps don't misalign.
    g = fin.set_index("qidx")["rev_yoy"]
    r = rets.set_index("qidx")["abn_ret"]
    df["rev_yoy_prev"] = [g.get(q - 1, np.nan) for q in df["qidx"]]
    df["abn_ret_next"] = [r.get(q + 1, np.nan) for q in df["qidx"]]
    df.insert(0, "ticker", company.ticker)
    num = df.columns.drop(["ticker", "quarter", "end", "earn_date"])
    df[num] = df[num].apply(pd.to_numeric, errors="coerce")
    return df


def add_sales_surprise(panel: pd.DataFrame) -> pd.DataFrame:
    """sales_surprise = year-over-year growth minus a forecast from the previous quarter's growth.

    Growth persists from quarter to quarter but partly reverts, so the forecast is a pooled regression
    of growth on last quarter's growth, each relative to the company's own average. What's left is the
    part of growth that last quarter didn't predict. The regression uses all years, which is fine for a
    backtest of signals but would need a rolling fit for live use.
    """
    p = panel.copy()
    mean = p.groupby("ticker")["rev_yoy"].transform("mean")
    y, x = p["rev_yoy"] - mean, p["rev_yoy_prev"] - mean
    ok = x.notna() & y.notna() & (x.abs() < 2) & (y.abs() < 2)  # skip extreme jumps (acquisitions, COVID)
    slope = float(np.polyfit(x[ok], y[ok], 1)[0]) if ok.sum() > 10 else 0.0
    p["sales_surprise"] = y - slope * x
    s = p.set_index(["ticker", "qidx"])["sales_surprise"]
    p["sales_surprise_next"] = [s.get((t, q + 1), np.nan) for t, q in zip(p["ticker"], p["qidx"])]
    p.attrs["growth_persistence"] = slope
    return p


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
    """Two-sided p-value for Spearman rho, shuffling x within each group.

    Spearman rho is the correlation of ranks, and shuffling x within groups only reorders its ranks, so the
    ranks are computed once and all shuffles are scored in one matrix product.
    """
    rng = np.random.default_rng(seed)
    rx, ry = stats.rankdata(x), stats.rankdata(y)
    rx, ry = rx - rx.mean(), ry - ry.mean()
    obs = abs(rx @ ry)
    perm = np.tile(np.arange(len(x)), (n, 1))
    for g in np.unique(groups):
        idx = np.flatnonzero(groups == g)
        perm[:, idx] = idx[np.argsort(rng.random((n, len(idx))), axis=1)]
    hits = int((np.abs(rx[perm] @ ry) >= obs - 1e-9).sum())
    return (hits + 1) / (n + 1)


def q_values(p: pd.Series) -> pd.Series:
    """Benjamini-Hochberg: the false-discovery rate at which each test would count as a finding."""
    p = p.astype(float)
    order = p.sort_values()
    m = len(order)
    q = (order * m / np.arange(1, m + 1))[::-1].cummin()[::-1].clip(upper=1)
    return q.reindex(p.index)


def test(panel: pd.DataFrame, signal: str, outcome: str, n_perm: int = 2000) -> Result | None:
    """Pooled test of one signal against one outcome. n_perm=0 skips the luck test (perm_p is NaN)."""
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
                  permutation_p(x, y, d["ticker"].to_numpy(), n_perm) if n_perm else np.nan,
                  float(s_neg), float(s_pos))


def run(panel: pd.DataFrame) -> pd.DataFrame:
    """Pooled and per-company results for every signal/outcome pair."""
    rows = []
    for name, sub in [("All companies", panel)] + list(panel.groupby("ticker")):
        for signal in SIGNALS:
            for outcome in OUTCOMES:
                r = test(sub, signal, outcome)
                if r:
                    rows.append({"scope": name, **r.__dict__})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Correct for the number of tests: pooled tests as one family, per-company tests as another.
    pooled = out["scope"] == "All companies"
    out["q_value"] = pd.concat([q_values(out.loc[pooled, "perm_p"]), q_values(out.loc[~pooled, "perm_p"])])
    return out


def robustness(panel: pd.DataFrame, signal: str, outcome: str, split_year: int = 2020) -> pd.DataFrame:
    """Does a pooled result hold up? Re-run it on halves of the data and without each company.

    Splits: two halves of the companies (alternating by ticker), quarters before / from `split_year`
    (fiscal year), plus the range of correlations when any one company is left out and the share of
    companies whose own correlation points the same way as the pooled one.
    """
    tickers = sorted(panel["ticker"].unique())
    halves = {"companies, half A": tickers[0::2], "companies, half B": tickers[1::2]}
    year = panel["qidx"] // 4
    parts = {**{k: panel[panel["ticker"].isin(v)] for k, v in halves.items()},
             f"fiscal years before {split_year}": panel[year < split_year],
             f"fiscal years {split_year} on": panel[year >= split_year]}
    rows = []
    for name, sub in parts.items():
        r = test(sub, signal, outcome)
        if r:
            rows.append({"check": name, "n": r.n, "rho": r.rho, "perm_p": r.perm_p})
    loo = [r.rho for t in tickers if (r := test(panel[panel["ticker"] != t], signal, outcome, n_perm=0))]
    own = [r.rho for t in tickers if (r := test(panel[panel["ticker"] == t], signal, outcome, n_perm=0))]
    pooled = test(panel, signal, outcome, n_perm=0)
    if loo:
        rows.append({"check": f"leave one company out (lowest / highest of {len(loo)})",
                     "n": pooled.n, "rho": min(loo), "perm_p": np.nan, "rho_high": max(loo)})
    if own:
        same = sum(np.sign(x) == np.sign(pooled.rho) for x in own)
        rows.append({"check": f"companies pointing the same way: {same} of {len(own)}",
                     "n": pooled.n, "rho": np.nan, "perm_p": np.nan})
    out = pd.DataFrame(rows)
    out.insert(0, "test", f"{signal} vs {outcome}")
    return out


def describe(rho: float, perm_p: float, q: float | None = None) -> str:
    strength = abs(rho)
    size = ("no" if strength < 0.05 else "a very weak" if strength < 0.1 else "a weak" if strength < 0.25 else "a moderate" if strength < 0.5 else "a strong")
    direction = "" if size == "no" else (" link in the predicted direction" if rho > 0
                                         else " link in the OPPOSITE direction")
    if q is not None and not np.isnan(q):
        luck = ("holds up after allowing for the number of tests" if q < 0.05 else
                "could be luck, given how many tests were run" if perm_p < 0.05 else
                "could easily be luck" if perm_p > 0.2 else "borderline")
    else:
        luck = ("unlikely to be luck" if perm_p < 0.05 else
                "could easily be luck" if perm_p > 0.2 else "borderline")
    return f"{size}{direction or ' link'} ({luck})"


def verdict(results: pd.DataFrame) -> str:
    """Plain-language summary of the pooled tests, one line per signal and outcome."""
    pooled = results[results["scope"] == "All companies"]
    if pooled.empty:
        return "Not enough data to test yet."
    lines = []
    for r in pooled.itertuples():
        q = getattr(r, "q_value", None)
        lines.append(f"{r.signal.capitalize()} vs {r.outcome}: {describe(r.rho, r.perm_p, q)}. "
                     f"Correlation {r.rho:+.2f}, {r.n} company-quarters, luck p={r.perm_p:.3f}"
                     + (f", q={q:.3f}." if q is not None else "."))
    return "\n".join(lines)
