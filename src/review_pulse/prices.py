"""Daily prices from Yahoo Finance and quarterly abnormal returns (stock minus SPY)."""

import pandas as pd

from .config import PRICES, Company
from .quarters import quarter_bounds

MARKET = "SPY"


def download(ticker: str, start: str, end: str) -> pd.Series:
    import yfinance as yf

    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        raise SystemExit(f"No price data for {ticker} from Yahoo Finance.")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):  # newer yfinance returns one column per ticker
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.rename(ticker)


def period_return(close: pd.Series, start, end) -> float | None:
    """Return from the last close before `start` to the last close on or before `end`."""
    before = close[close.index < pd.Timestamp(start)]
    upto = close[close.index <= pd.Timestamp(end)]
    if before.empty or upto.empty or upto.index[-1] < pd.Timestamp(start):
        return None
    return float(upto.iloc[-1] / before.iloc[-1] - 1)


def quarterly_returns(close: pd.Series, market: pd.Series, qidxs: list[int],
                      fy_end_month: int) -> pd.DataFrame:
    rows = []
    for q in qidxs:
        fy, fq = divmod(q, 4)
        start, end = quarter_bounds(fy, fq + 1, fy_end_month)
        r = period_return(close, start, end)
        m = period_return(market, start, end)
        rows.append({"qidx": q, "ret": r, "mkt_ret": m,
                     "abn_ret": None if r is None or m is None else r - m})
    return pd.DataFrame(rows)


def fetch(company: Company, start: str, end: str) -> None:
    PRICES.mkdir(parents=True, exist_ok=True)
    # Pad the window: returns need the close before each quarter, and next-quarter returns
    # run past the review window.
    s = (pd.Timestamp(start) - pd.DateOffset(months=15)).strftime("%Y-%m-%d")
    e = (pd.Timestamp(end) + pd.DateOffset(months=9)).strftime("%Y-%m-%d")
    for t in (company.ticker, MARKET):
        path = PRICES / f"{t}.parquet"
        download(t, s, e).to_frame("close").to_parquet(path)
    print(f"{company.ticker}: prices saved")


def load(ticker: str) -> pd.Series:
    path = PRICES / f"{ticker}.parquet"
    if not path.exists():
        raise SystemExit(f"No prices for {ticker}. Run: review-pulse fetch --company {ticker}")
    return pd.read_parquet(path)["close"]
