"""Stock move around each results announcement: the market's verdict on a quarter.

Companies announce quarterly results in an 8-K filing with item 2.02. The move is measured from the last
close before the filing date to the close of the second trading day from it, minus SPY over the same days.
That covers announcements made before the open and after the close. Each announcement is matched to the
fiscal quarter it reports on: the latest quarter that ended 5 to 120 days before it.

Analysts' estimates aren't free, so this is the closest free measure of a "surprise": the price already
reflects what investors expected, and the move shows how far the results differed.
"""

import pandas as pd

from .config import DATA, Company
from .filings import filing_index
from .financials import company_cik
from .quarters import fiscal_quarter, qidx, quarter_bounds

EARNINGS = DATA / "earnings"


def fetch(company: Company) -> None:
    idx = filing_index(company_cik(company), {"8-K", "8-K/A"})
    idx = idx[idx["items"].fillna("").str.contains("2.02", regex=False)]
    EARNINGS.mkdir(parents=True, exist_ok=True)
    idx[["accessionNumber", "filingDate", "form", "items"]].to_parquet(EARNINGS / f"{company.ticker}.parquet", index=False)
    print(f"{company.ticker}: {len(idx)} results announcements")


def reported_quarter(day: pd.Timestamp, fy_end_month: int) -> int | None:
    """qidx of the quarter an announcement on `day` reports: latest quarter ending 5-120 days before."""
    here = qidx(*fiscal_quarter(day.date(), fy_end_month))
    for cand in (here, here - 1, here - 2):  # most recent first
        cfy, cfq = divmod(cand, 4)
        _, end = quarter_bounds(cfy, cfq + 1, fy_end_month)
        gap = (day - pd.Timestamp(end)).days
        if 5 <= gap <= 120:
            return cand
    return None


def window_return(close: pd.Series, day: pd.Timestamp) -> float | None:
    before = close[close.index < day]
    after = close[close.index >= day]
    if before.empty or len(after) < 2:
        return None
    return float(after.iloc[1] / before.iloc[-1] - 1)


def quarterly(company: Company, close: pd.Series, market: pd.Series) -> pd.DataFrame:
    """qidx (the quarter reported), earn_date, earn_ret (abnormal move around the announcement)."""
    path = EARNINGS / f"{company.ticker}.parquet"
    cols = ["qidx", "earn_date", "earn_ret"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    rows = []
    for d in sorted(pd.to_datetime(pd.read_parquet(path)["filingDate"]).unique()):
        q = reported_quarter(pd.Timestamp(d), company.fy_end_month)
        r, m = window_return(close, d), window_return(market, d)
        if q is not None and r is not None and m is not None:
            rows.append({"qidx": q, "earn_date": d, "earn_ret": r - m})
    df = pd.DataFrame(rows, columns=cols)
    return df.drop_duplicates("qidx", keep="first")  # first announcement per quarter; later ones are amendments
