"""Quarterly revenue and net income from SEC EDGAR (companyfacts XBRL API).

Companies often report Q4 only inside the annual 10-K, so Q4 = full year - (Q1+Q2+Q3).
Values are taken as first reported (earliest filing), which is closer to what the market saw.
"""

import os
from datetime import timedelta

import pandas as pd
import requests
from dotenv import load_dotenv

from .config import FIN, ROOT, Company
from .quarters import period_end_quarter

REVENUE = ["RevenueFromContractWithCustomerExcludingAssessedTax",
           "RevenueFromContractWithCustomerIncludingAssessedTax",
           "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"]
NET_INCOME = ["NetIncomeLoss", "ProfitLoss"]
FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "10-KT"}


def _headers() -> dict:
    load_dotenv(ROOT / ".env")
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua:
        raise SystemExit("SEC EDGAR needs a contact. Copy .env.example to .env and set "
                         'SEC_USER_AGENT="Your Name your-email@example.com".')
    return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}


def company_cik(company: Company) -> int:
    return int(company.cik) if company.cik else cik_for(company.ticker)


def cik_for(ticker: str) -> int:
    r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=_headers(), timeout=30)
    r.raise_for_status()
    for row in r.json().values():
        if row["ticker"].upper() == ticker.upper():
            return int(row["cik_str"])
    raise SystemExit(f"Ticker {ticker} not found at SEC (it may have been delisted or renamed). "
                     "Add its SEC CIK to config/companies.yaml as `cik:`.")


def company_facts(cik: int) -> dict:
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    r = requests.get(url, headers=_headers(), timeout=60)
    r.raise_for_status()
    return r.json()


def _entries(facts: dict, concepts: list[str]) -> pd.DataFrame:
    """All USD duration entries for the concepts; earlier concept in the list wins for the same period."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    frames = []
    for rank, concept in enumerate(concepts):
        for e in gaap.get(concept, {}).get("units", {}).get("USD", []):
            if "start" not in e or e.get("form") not in FORMS:
                continue
            frames.append({"start": e["start"], "end": e["end"], "val": float(e["val"]),
                           "filed": e["filed"], "rank": rank})
    if not frames:
        return pd.DataFrame(columns=["start", "end", "val", "filed", "days"])
    df = pd.DataFrame(frames)
    for c in ("start", "end", "filed"):
        df[c] = pd.to_datetime(df[c]).dt.date
    df["days"] = [(e - s).days for s, e in zip(df["start"], df["end"])]
    # Best concept, then first reported.
    df = df.sort_values(["start", "end", "rank", "filed"]).drop_duplicates(["start", "end"])
    return df.drop(columns="rank")


def quarterly_series(facts: dict, concepts: list[str]) -> pd.DataFrame:
    """One row per fiscal quarter: start, end, val, filed. Derives missing Q4s from annual totals."""
    df = _entries(facts, concepts)
    quarters = df[df["days"].between(75, 105)]
    annual = df[df["days"].between(340, 380)]
    rows = quarters[["start", "end", "val", "filed"]].to_dict("records")
    have_end = {r["end"] for r in rows}
    for a in annual.itertuples():
        if a.end in have_end:
            continue
        inside = quarters[(quarters["start"] >= a.start - timedelta(days=7)) & (quarters["end"] <= a.end)]
        inside = inside.drop_duplicates("end")
        if len(inside) != 3:
            continue
        q3_end = max(inside["end"])
        rows.append({"start": q3_end + timedelta(days=1), "end": a.end,
                     "val": a.val - inside["val"].sum(), "filed": a.filed})
        have_end.add(a.end)
    return pd.DataFrame(rows, columns=["start", "end", "val", "filed"])


def build(company: Company) -> pd.DataFrame:
    facts = company_facts(company_cik(company))
    return from_facts(facts, company)


def from_facts(facts: dict, company: Company) -> pd.DataFrame:
    rev = quarterly_series(facts, REVENUE).rename(columns={"val": "revenue"})
    ni = quarterly_series(facts, NET_INCOME).rename(columns={"val": "net_income", "filed": "ni_filed"})
    if rev.empty:
        raise SystemExit(f"{company.ticker}: no revenue found in EDGAR XBRL facts.")
    df = rev.merge(ni[["end", "net_income"]], on="end", how="left")
    fq = [period_end_quarter(e, company.fy_end_month) for e in df["end"]]
    df["fy"] = [a for a, _ in fq]
    df["fq"] = [b for _, b in fq]
    df["qidx"] = df["fy"] * 4 + df["fq"] - 1
    df["quarter"] = "FY" + df["fy"].astype(str) + "Q" + df["fq"].astype(str)
    df = df.sort_values(["qidx", "filed"]).drop_duplicates("qidx").reset_index(drop=True)
    return add_growth(df)


def add_growth(df: pd.DataFrame) -> pd.DataFrame:
    """rev_yoy: revenue vs same quarter last year. growth_change: rev_yoy minus last quarter's rev_yoy."""
    by_q = df.set_index("qidx")["revenue"]
    df = df.copy()
    df["rev_yoy"] = [by_q[q] / by_q[q - 4] - 1 if (q - 4) in by_q.index and by_q[q - 4] else None
                     for q in df["qidx"]]
    yoy = df.set_index("qidx")["rev_yoy"]
    df["growth_change"] = [yoy[q] - yoy[q - 1] if (q - 1) in yoy.index else None for q in df["qidx"]]
    df[["rev_yoy", "growth_change"]] = df[["rev_yoy", "growth_change"]].astype(float)
    return df


def fetch(company: Company) -> pd.DataFrame:
    FIN.mkdir(parents=True, exist_ok=True)
    df = build(company)
    df.to_parquet(FIN / f"{company.ticker}.parquet", index=False)
    print(f"{company.ticker}: {len(df)} quarters of financials ({df['quarter'].iloc[0]} to {df['quarter'].iloc[-1]})")
    return df


def load(ticker: str) -> pd.DataFrame:
    path = FIN / f"{ticker}.parquet"
    if not path.exists():
        raise SystemExit(f"No financials for {ticker}. Run: alternative-signals fetch --company {ticker}")
    return pd.read_parquet(path)

