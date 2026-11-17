"""Wikipedia pageviews as a consumer-interest signal.

Monthly views (human users, all platforms) for each company's articles, summed per fiscal quarter.
Signal: wiki_yoy = log(views this quarter / views same quarter last year). Comparing against the
same quarter a year earlier removes seasonality such as holiday spikes. Data starts July 2015.
"""

import time

import numpy as np
import pandas as pd
import requests

from .config import DATA, Company
from .quarters import add_quarter_columns

WIKI = DATA / "wiki"
API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/"
       "all-access/user/{article}/monthly/2015070100/{end}")
HEADERS = {"User-Agent": "alternative-signals/0.1 (https://github.com/Siddigz/alternative-signals; research script)"}


def article_views(article: str, end: str, retries: int = 6) -> pd.DataFrame:
    url = API.format(article=requests.utils.quote(article.replace(" ", "_"), safe=""), end=end)
    for attempt in range(retries):
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After", 2 ** attempt)))
            continue
        if r.status_code == 404:
            print(f"  Wikipedia article not found or no views: {article}")
            return pd.DataFrame(columns=["month", "views"])
        r.raise_for_status()
        items = r.json().get("items", [])
        return pd.DataFrame({"month": pd.to_datetime([i["timestamp"][:8] for i in items]),
                             "views": [i["views"] for i in items]})
    raise RuntimeError(f"Wikipedia kept rate-limiting requests for {article}")


def fetch(company: Company) -> None:
    if not company.wiki:
        return
    end = pd.Timestamp.today().strftime("%Y%m0100")
    frames = []
    for a in company.wiki:
        v = article_views(a, end)
        v["article"] = a
        frames.append(v)
        time.sleep(0.5)
    WIKI.mkdir(parents=True, exist_ok=True)
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(WIKI / f"{company.ticker}.parquet", index=False)
    print(f"{company.ticker}: Wikipedia views for {df['article'].nunique()} article(s), {len(df)} article-months")


def quarterly(company: Company) -> pd.DataFrame:
    """qidx, wiki_views, wiki_yoy. Quarters with any missing month are dropped."""
    path = WIKI / f"{company.ticker}.parquet"
    cols = ["qidx", "wiki_views", "wiki_yoy"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_parquet(path)
    if df.empty:
        return pd.DataFrame(columns=cols)
    # Only count an article from its first full year of data, so new articles don't look like growth.
    total = df.groupby("month")["views"].sum().reset_index()
    total = add_quarter_columns(total, "month", company.fy_end_month)
    q = total.groupby("qidx").agg(wiki_views=("views", "sum"), months=("views", "size"))
    q = q[q["months"] == 3]
    # First quarter in which every article has data for all three months.
    latest_start = pd.DataFrame({"m": [df.groupby("article")["month"].min().max()]})
    latest_start = add_quarter_columns(latest_start, "m", company.fy_end_month)
    starts_quarter = (latest_start["m"].dt.month.iloc[0] - company.fy_end_month - 1) % 3 == 0
    stable_from = latest_start["qidx"].iloc[0] + (0 if starts_quarter else 1)
    views = q["wiki_views"]
    yoy = [np.log(views[i] / views[i - 4]) if (i - 4) in views.index and i - 4 >= stable_from
           and views[i - 4] > 0 else np.nan for i in views.index]
    return pd.DataFrame({"qidx": views.index, "wiki_views": views.values, "wiki_yoy": yoy})
