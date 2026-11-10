"""Wording of 10-K and 10-Q filings as a signal.

For each filing, count negative words (decline, impairment, headwinds, ...) and uncertainty words
(uncertain, volatility, ...) per 1,000 words. A filing is placed in the fiscal quarter it was
*filed* in, so the signal is known by the end of that quarter. Signal: filing_chg = rate now minus
the rate a year earlier (same filing type, so a 10-K is compared with the previous 10-K).
More negative wording is expected to come before weaker results, so the expected sign is negative.
"""

import html
import re
import time

import numpy as np
import pandas as pd
import requests

from .config import DATA, Company
from .financials import _headers, company_cik
from .quarters import add_quarter_columns

FILINGS = DATA / "filings"
NEGATIVE = re.compile(
    r"\b(?:loss(?:es)?|declin\w*|decreas\w*|weak\w*|advers\w*|impair\w*|litigat\w*|headwind\w*|"
    r"challeng\w*|difficult\w*|shortfall\w*|deteriorat\w*|unfavorabl\w*|restructur\w*|layoff\w*|"
    r"downturn\w*|slowdown\w*|disrupt\w*|shortage\w*|softness|softer|softening)\b")
UNCERTAIN = re.compile(r"\b(?:uncertain\w*|volatil\w*|unpredictab\w*|fluctuat\w*)\b")
WORD = re.compile(r"\b[a-z]{2,}\b")
TAG = re.compile(r"<[^>]+>")
HIDDEN = re.compile(r"<(script|style|ix:header)[^>]*>.*?</\1>", re.S | re.I)
FORMS = {"10-K", "10-Q"}


def word_rates(raw_html: str) -> dict:
    text = html.unescape(TAG.sub(" ", HIDDEN.sub(" ", raw_html))).lower()
    words = len(WORD.findall(text))
    if not words:
        return {"words": 0, "neg_rate": np.nan, "unc_rate": np.nan}
    return {"words": words,
            "neg_rate": 1000 * len(NEGATIVE.findall(text)) / words,
            "unc_rate": 1000 * len(UNCERTAIN.findall(text)) / words}


def filing_index(cik: int, forms: set[str] = FORMS) -> pd.DataFrame:
    """All filings of the given form types, from the SEC submissions API."""
    def get(url):
        time.sleep(0.15)  # SEC allows 10 requests/second
        r = requests.get(url, headers=_headers(), timeout=60)
        r.raise_for_status()
        return r.json()

    sub = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    parts = [pd.DataFrame(sub["filings"]["recent"])]
    for f in sub["filings"].get("files", []):
        parts.append(pd.DataFrame(get(f"https://data.sec.gov/submissions/{f['name']}")))
    df = pd.concat(parts, ignore_index=True)
    df = df[df["form"].isin(forms)]
    return df[["accessionNumber", "filingDate", "reportDate", "form", "items", "primaryDocument"]]


def fetch(company: Company, start: str) -> None:
    FILINGS.mkdir(parents=True, exist_ok=True)
    path = FILINGS / f"{company.ticker}.parquet"
    cached = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=["accessionNumber"])
    cik = company_cik(company)
    idx = filing_index(cik)
    # One year before the window so the first year-over-year comparison exists.
    idx = idx[idx["filingDate"] >= str(pd.Timestamp(start) - pd.DateOffset(years=1))[:10]]
    todo = idx[~idx["accessionNumber"].isin(cached["accessionNumber"])]
    rows = []
    for f in todo.itertuples():
        url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/"
               f"{f.accessionNumber.replace('-', '')}/{f.primaryDocument}")
        time.sleep(0.15)
        r = requests.get(url, headers=_headers(), timeout=120)
        if r.status_code != 200:
            print(f"  skipped {f.form} {f.filingDate}: HTTP {r.status_code}")
            continue
        rows.append({"accessionNumber": f.accessionNumber, "filingDate": f.filingDate,
                     "reportDate": f.reportDate, "form": f.form, **word_rates(r.text)})
    df = pd.concat([cached, pd.DataFrame(rows)], ignore_index=True) if rows else cached
    df.to_parquet(path, index=False)
    print(f"{company.ticker}: {len(df)} filings scored ({len(rows)} new)")


def quarterly(company: Company) -> pd.DataFrame:
    """qidx, neg_rate, unc_rate, filing_chg (change in negative+uncertainty rate vs a year earlier)."""
    path = FILINGS / f"{company.ticker}.parquet"
    cols = ["qidx", "neg_rate", "unc_rate", "filing_chg"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_parquet(path)
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = add_quarter_columns(df, "filingDate", company.fy_end_month)
    df = df.sort_values("filingDate").drop_duplicates("qidx", keep="first")  # skip amendments/duplicates
    df["rate"] = df["neg_rate"] + df["unc_rate"]
    by_q = df.set_index("qidx")
    df["filing_chg"] = [r - by_q.at[q - 4, "rate"]
                        if (q - 4) in by_q.index and by_q.at[q - 4, "form"] == f else np.nan
                        for q, r, f in zip(df["qidx"], df["rate"], df["form"])]
    return df[cols]
