"""Insider buying and selling, from SEC Form 4 filings.

Directors and officers must report trades in their company's stock within two business days on Form 4.
Open-market purchases (code P) are the informative ones: insiders buy with their own money for one
reason. Sales (code S) happen for many reasons, so they carry less.

Signal per fiscal quarter, using filings made in that quarter:
  insider_npr = (insiders buying - insiders selling) / (insiders buying + insiders selling)
It runs from -1 (only sellers) to +1 (only buyers), and is missing in quarters with no trades.
Expected sign: positive.
"""

import time
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import requests

from .config import DATA, Company
from .filings import filing_index
from .financials import _headers, company_cik
from .quarters import add_quarter_columns

INSIDERS = DATA / "insiders"
COLS = ["accessionNumber", "filingDate", "owner", "code", "shares", "price"]


def _text(node, path: str) -> str | None:
    el = node.find(path)
    return el.text.strip() if el is not None and el.text else None


def parse_form4(xml: str) -> list[dict]:
    """Open-market buys and sells (codes P and S) in one Form 4."""
    root = ET.fromstring(xml)
    owner = _text(root, "reportingOwner/reportingOwnerId/rptOwnerCik") or "?"
    rows = []
    for t in root.iter("nonDerivativeTransaction"):
        code = _text(t, "transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue
        shares = _text(t, "transactionAmounts/transactionShares/value")
        price = _text(t, "transactionAmounts/transactionPricePerShare/value")
        rows.append({"owner": owner, "code": code,
                     "shares": float(shares) if shares else np.nan,
                     "price": float(price) if price else np.nan})
    return rows


def fetch(company: Company, start: str) -> None:
    INSIDERS.mkdir(parents=True, exist_ok=True)
    path = INSIDERS / f"{company.ticker}.parquet"
    cached = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=COLS + ["done"])
    cik = company_cik(company)
    idx = filing_index(cik, {"4", "4/A"})
    idx = idx[idx["filingDate"] >= str(pd.Timestamp(start) - pd.DateOffset(years=1))[:10]]
    todo = idx[~idx["accessionNumber"].isin(cached["accessionNumber"])]
    rows = []
    for f in todo.itertuples():
        doc = f.primaryDocument.split("/")[-1]  # drop the "xslF345X0n/" styled-view folder to get raw XML
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{f.accessionNumber.replace('-', '')}/{doc}"
        time.sleep(0.12)
        r = requests.get(url, headers=_headers(), timeout=60)
        trades = []
        if r.status_code == 200:
            try:
                trades = parse_form4(r.text)
            except ET.ParseError:
                pass
        base = {"accessionNumber": f.accessionNumber, "filingDate": f.filingDate}
        # One marker row per filing so filings without trades aren't downloaded again.
        rows += [{**base, **t, "done": True} for t in trades] or [{**base, "done": True}]
    df = pd.concat([cached, pd.DataFrame(rows)], ignore_index=True) if rows else cached
    df.to_parquet(path, index=False)
    trades = df.dropna(subset=["code"]) if "code" in df else df
    print(f"{company.ticker}: {df['accessionNumber'].nunique()} Form 4 filings, "
          f"{(trades['code'] == 'P').sum()} buys, {(trades['code'] == 'S').sum()} sells ({len(todo)} new)")


def quarterly(company: Company) -> pd.DataFrame:
    """qidx, insider_buyers, insider_sellers, insider_npr."""
    path = INSIDERS / f"{company.ticker}.parquet"
    cols = ["qidx", "insider_buyers", "insider_sellers", "insider_npr"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_parquet(path).dropna(subset=["code"])
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = add_quarter_columns(df, "filingDate", company.fy_end_month)
    g = df.groupby("qidx")
    out = pd.DataFrame({
        "insider_buyers": g.apply(lambda x: x.loc[x["code"] == "P", "owner"].nunique(), include_groups=False),
        "insider_sellers": g.apply(lambda x: x.loc[x["code"] == "S", "owner"].nunique(), include_groups=False),
    }).reset_index()
    total = out["insider_buyers"] + out["insider_sellers"]
    out["insider_npr"] = (out["insider_buyers"] - out["insider_sellers"]) / total.where(total > 0)
    return out[cols]
