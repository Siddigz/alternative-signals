"""Short interest from FINRA: how many shares traders have borrowed and sold, betting the price falls.

FINRA publishes each stock's short position twice a month (free, no key; data from Dec 2017).
Signal per fiscal quarter: short_dtc = "days to cover" (short position / average daily volume) at the
last report in the quarter. Pooled tests compare each company with its own norm, so this asks whether
quarters with more short selling than usual come before worse outcomes. Expected sign: negative.
"""

import time

import pandas as pd
import requests

from .config import DATA, Company
from .quarters import add_quarter_columns

SHORTS = DATA / "short_interest"
API = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"


def _reports(symbol: str) -> list[dict]:
    body = {"limit": 5000, "compareFilters": [
        {"compareType": "equal", "fieldName": "symbolCode", "fieldValue": symbol}]}
    for attempt in range(5):
        r = requests.post(API, json=body, headers={"Accept": "application/json"}, timeout=60)
        if r.status_code != 429:
            break
        time.sleep(2 ** attempt)
    r.raise_for_status()
    return r.json() if r.text.strip() else []


def fetch(company: Company) -> None:
    rows = [x for sym in [company.ticker, *company.former_tickers] for x in _reports(sym)]
    df = pd.DataFrame(rows)
    if len(df):
        df = df.drop_duplicates("settlementDate", keep="first")
    if df.empty:
        print(f"{company.ticker}: no FINRA short interest")
        df = pd.DataFrame(columns=["settlementDate", "currentShortPositionQuantity",
                                   "averageDailyVolumeQuantity", "daysToCoverQuantity"])
    df = df[["settlementDate", "currentShortPositionQuantity", "averageDailyVolumeQuantity",
             "daysToCoverQuantity"]].sort_values("settlementDate")
    SHORTS.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SHORTS / f"{company.ticker}.parquet", index=False)
    print(f"{company.ticker}: {len(df)} short-interest reports"
          + (f" ({df['settlementDate'].iloc[0]} to {df['settlementDate'].iloc[-1]})" if len(df) else ""))


def quarterly(company: Company) -> pd.DataFrame:
    """qidx, short_dtc (days to cover at the quarter's last report)."""
    path = SHORTS / f"{company.ticker}.parquet"
    cols = ["qidx", "short_dtc"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_parquet(path)
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = add_quarter_columns(df, "settlementDate", company.fy_end_month)
    last = df.sort_values("settlementDate").groupby("qidx").tail(1)
    return pd.DataFrame({"qidx": last["qidx"].values,
                         "short_dtc": pd.to_numeric(last["daysToCoverQuantity"], errors="coerce").values})
