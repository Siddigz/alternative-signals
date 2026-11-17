"""Google search interest (Google Trends) as a consumer-interest signal.

Monthly US search interest for up to five brand terms, fetched in one request so they share a scale,
from 2015 to today. Signal: trends_yoy = log(interest this quarter / same quarter a year earlier),
like the Wikipedia signal. Expected sign: positive.

Google Trends has no official API; this uses the unofficial `pytrends` client, which Google rate-limits.
"""

import time

import numpy as np
import pandas as pd

from .config import DATA, Company
from .quarters import add_quarter_columns

TRENDS = DATA / "trends"


def fetch(company: Company, start: str = "2015-01-01") -> None:
    from pytrends.request import TrendReq

    terms = company.trends[:5]
    if not terms:
        return
    timeframe = f"{start} {pd.Timestamp.today():%Y-%m-%d}"
    for attempt in range(6):
        try:
            p = TrendReq(hl="en-US", tz=0, timeout=(10, 30))
            p.build_payload(terms, timeframe=timeframe, geo="US")
            df = p.interest_over_time()
            break
        except Exception as e:  # pytrends raises on 429 "too many requests"
            if attempt == 5:
                raise RuntimeError(f"Google Trends kept refusing requests for {terms}: {e}")
            time.sleep(10 * 2 ** attempt)
    if df.empty:
        print(f"{company.ticker}: no Google Trends data for {terms}")
        return
    df = df[~df["isPartial"]] if "isPartial" in df else df
    out = pd.DataFrame({"month": df.index, "interest": df[terms].sum(axis=1).values})
    TRENDS.mkdir(parents=True, exist_ok=True)
    out.to_parquet(TRENDS / f"{company.ticker}.parquet", index=False)
    print(f"{company.ticker}: Google Trends for {terms}, {len(out)} months")
    time.sleep(3)


def quarterly(company: Company) -> pd.DataFrame:
    """qidx, trends, trends_yoy. Quarters with a missing month are dropped."""
    path = TRENDS / f"{company.ticker}.parquet"
    cols = ["qidx", "trends", "trends_yoy"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = add_quarter_columns(pd.read_parquet(path), "month", company.fy_end_month)
    q = df.groupby("qidx").agg(trends=("interest", "sum"), months=("interest", "size"))
    q = q[q["months"] == 3]["trends"]
    yoy = [np.log(q[i] / q[i - 4]) if (i - 4) in q.index and q[i - 4] > 0 and q[i] > 0 else np.nan
           for i in q.index]
    return pd.DataFrame({"qidx": q.index, "trends": q.values, "trends_yoy": yoy})
