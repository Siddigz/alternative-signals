"""House members' stock trades from their STOCK Act periodic transaction reports (PTRs).

The House Clerk publishes a yearly index of every disclosure (financial-pdfs/{year}FD.zip) and each PTR
as a PDF (ptr-pdfs/{year}/{DocID}.pdf). Reports filed electronically (DocID starting with 2) have a
text layer and are parsed here. Paper reports are scanned images with no text, so they are counted but
not read (they would need OCR).

Each transaction line looks like
    SP Palo Alto Networks, Inc. (PANW) P 02/12/2024 02/12/2024 $500,001 -
    [OP] $1,000,000
i.e. owner, asset, ticker, asset type, P/S/E, trade date, notification date, amount range.
The disclosure date used for copying is the report's filing date from the index.
"""

import io
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import date

import numpy as np
import pandas as pd
import requests

from .config import DATA

BASE = "https://disclosures-clerk.house.gov/public_disc"
HEADERS = {"User-Agent": "alternative-signals/0.1 (research script)"}
DIR = DATA / "congress"
FIRST_YEAR = 2014  # electronic filing began in 2014

TX = re.compile(r"\s(P|S(?: \(partial\))?|E)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}/\d{1,2}/\d{4})\b(.*)$")
STATUS = re.compile(r"^(F\s*S\s*:|FILING STATUS|\* For the complete|ASSET CLASS|ID OWNER)", re.I)
DESC = re.compile(r"^(D\s*:|DESCRIPTION:)\s*(.*)", re.I)
TICKER = re.compile(r"\(([A-Za-z][A-Za-z0-9.\-]{0,7})\)")
TYPE = re.compile(r"\[([A-Za-z]{2})\]")
MONEY = re.compile(r"\$([\d,]+)")


def _get(url: str, tries: int = 7, **kw) -> requests.Response:
    """GET with retries, waiting 5, 10, 20, ... seconds, so a brief network dropout doesn't stop a long run."""
    for n in range(tries):
        last = n == tries - 1
        try:
            r = requests.get(url, timeout=60, **kw)
        except (requests.ConnectionError, requests.Timeout):
            if last:
                raise
        else:
            if r.status_code not in (429, 500, 502, 503, 504) or last:
                r.raise_for_status()
                return r
        time.sleep(5 * 2 ** n)
    raise RuntimeError("unreachable")


def index(year: int) -> pd.DataFrame:
    """Every PTR filed in `year` (cached once the year is over)."""
    DIR.mkdir(parents=True, exist_ok=True)
    path = DIR / f"index_{year}.parquet"
    if path.exists() and year < date.today().year:
        return pd.read_parquet(path)
    r = _get(f"{BASE}/financial-pdfs/{year}FD.zip", headers=HEADERS)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        root = ET.fromstring(z.read(f"{year}FD.xml").decode("utf-8-sig"))
    rows = [{c.tag: (c.text or "").strip() for c in m} for m in root]
    df = pd.DataFrame(rows)
    df = df[df["FilingType"] == "P"].copy()
    df["member"] = (df["First"].str.rstrip(".") + " " + df["Last"]).str.strip()
    df["filed"] = pd.to_datetime(df["FilingDate"], format="%m/%d/%Y")
    df["year"] = year
    df["electronic"] = df["DocID"].str.startswith("2")
    df = df.rename(columns={"DocID": "doc_id", "StateDst": "district"})
    df = df[["doc_id", "member", "district", "year", "filed", "electronic"]].reset_index(drop=True)
    df.to_parquet(path, index=False)
    return df


def pdf_text(year: int, doc_id: str) -> str:
    import pdfplumber

    r = _get(f"{BASE}/ptr-pdfs/{year}/{doc_id}.pdf", headers=HEADERS)
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _date(s: str) -> pd.Timestamp:
    return pd.to_datetime(s, format="%m/%d/%Y", errors="coerce")


def parse(text: str) -> list[dict]:
    """Transactions in one report's text."""
    text = text.replace(chr(0), "")  # some fonts extract heading letters as nulls
    lines = [re.sub(r"[ 	]+", " ", ln).strip() for ln in text.splitlines()]
    out = []
    i = 0
    while i < len(lines):
        m = TX.search(" " + lines[i])
        if not m:
            i += 1
            continue
        head = (" " + lines[i])[: m.start()].strip()
        block = [head, m.group(4)]
        j = i + 1
        while j < len(lines) and not STATUS.match(lines[j]) and not TX.search(" " + lines[j]):
            block.append(lines[j])
            j += 1
        desc = ""
        k = j
        while k < len(lines) and k < j + 6 and not TX.search(" " + lines[k]):
            d = DESC.match(lines[k])
            if d:
                desc = d.group(2)
                break
            k += 1
        first, _, rest = head.partition(" ")
        owner = first if first in ("SP", "JT", "DC") else "self"
        if owner != "self":
            block[0] = rest
        joined = " ".join(block)
        tickers = TICKER.findall(joined)
        kind = TYPE.findall(joined)
        money = [int(x.replace(",", "")) for x in MONEY.findall(joined)]
        over = "over" in joined.lower() and len(money) == 1
        out.append({
            "owner": owner,
            "asset": re.sub(r"\s+", " ", TYPE.sub("", re.sub(r"\$[\d,]+\s*-?|Over|Spouse/DC|gfedcb?", "", joined))).strip(),
            "ticker": tickers[-1].upper() if tickers else None,
            "asset_type": kind[0].upper() if kind else None,
            "tx": m.group(1)[0],
            "partial": "partial" in m.group(1),
            "tx_date": _date(m.group(2)),
            "notified": _date(m.group(3)),
            "amt_low": money[0] if money else None,
            "amt_high": None if over or len(money) < 2 else money[1],
            "description": desc,
        })
        i = j
    return out


def fetch(years: list[int] | None = None, pause: float = 0.25) -> pd.DataFrame:
    """Download and parse every electronic PTR, keeping the text so the parser can be rerun offline."""
    years = years or list(range(FIRST_YEAR, date.today().year + 1))
    texts_path = DIR / "texts.parquet"
    texts = pd.read_parquet(texts_path) if texts_path.exists() else pd.DataFrame(columns=["doc_id", "year", "text"])
    have = set(texts["doc_id"])
    new = []
    for y in years:
        idx = index(y)
        todo = idx[idx["electronic"] & ~idx["doc_id"].isin(have)]
        print(f"{y}: {len(idx)} reports, {int(idx['electronic'].sum())} electronic, {len(todo)} to download")
        for n, doc in enumerate(todo["doc_id"], 1):
            try:
                new.append({"doc_id": doc, "year": y, "text": pdf_text(y, doc)})
            except Exception as e:  # keep going; a later run retries
                print(f"  {doc}: {e}")
            time.sleep(pause)
            if len(new) >= 200:
                texts = pd.concat([texts, pd.DataFrame(new)], ignore_index=True)
                texts.to_parquet(texts_path, index=False)
                new = []
                print(f"  {y}: {n}/{len(todo)}")
    if new:
        texts = pd.concat([texts, pd.DataFrame(new)], ignore_index=True)
        texts.to_parquet(texts_path, index=False)
    return build_trades()


HONORIFICS = {"mr", "mrs", "ms", "miss", "hon", "dr", "jr", "sr", "ii", "iii"}


def member_key(name: str) -> str:
    """First and last name only, so spellings like 'Marjorie Taylor Greene' and 'Marjorie Taylor Mrs Greene' match."""
    words = [w for w in re.split(r"[\s.,]+", name or "") if w and w.lower() not in HONORIFICS]
    return f"{words[0]} {words[-1]}".title() if len(words) > 1 else (name or "").title()


def build_trades() -> pd.DataFrame:
    """Parse all saved report texts into one trades table, joined to the index (member, filing date)."""
    texts = pd.read_parquet(DIR / "texts.parquet")
    idx = pd.concat([pd.read_parquet(p) for p in sorted(DIR.glob("index_*.parquet"))], ignore_index=True)
    rows = []
    for r in texts.itertuples():
        for t in parse(r.text):
            rows.append({"doc_id": r.doc_id, **t})
    trades = pd.DataFrame(rows).merge(idx.drop(columns=["electronic"]), on="doc_id", how="left")
    trades["member"] = trades["member"].map(member_key)
    trades["delay"] = (trades["filed"] - trades["tx_date"]).dt.days
    trades.to_parquet(DIR / "trades.parquet", index=False)
    print(f"{len(trades):,} transactions from {texts['doc_id'].nunique():,} reports, "
          f"{trades['member'].nunique()} members")
    return trades


def load_trades() -> pd.DataFrame:
    path = DIR / "trades.parquet"
    if not path.exists():
        raise SystemExit("No congress trades yet. Run: alternative-signals congress-fetch")
    return pd.read_parquet(path)


def coverage() -> pd.DataFrame:
    """Reports per year, electronic vs paper."""
    idx = pd.concat([pd.read_parquet(p) for p in sorted(DIR.glob("index_*.parquet"))], ignore_index=True)
    return idx.groupby("year").agg(reports=("doc_id", "size"), electronic=("electronic", "sum"),
                                   members=("member", "nunique"))


# ---- prices for every traded ticker -------------------------------------------------------------

def yahoo_symbol(ticker: str) -> str:
    return ticker.replace(".", "-")


def fetch_prices(tickers: list[str], start: str = "2013-06-01", chunk: int = 50, pause: float = 4.0) -> pd.DataFrame:
    """Daily adjusted closes for many tickers (wide table), cached and extended with new tickers.

    Tickers Yahoo has no data for (delisted, renamed) are remembered so they aren't asked again; tickers
    refused because of Yahoo's rate limit are retried after a longer wait.
    """
    import logging

    import yfinance as yf

    class Catch(logging.Handler):  # yfinance reports rate limits only through its log
        hit = False

        def emit(self, record):
            if "rate limit" in record.getMessage().lower():
                Catch.hit = True

    logging.getLogger("yfinance").addHandler(Catch())
    path = DIR / "prices.parquet"
    wide = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    want = sorted({yahoo_symbol(t) for t in tickers} | {"SPY", "QQQ"})
    tried_path = DIR / "prices_tried.txt"
    tried = set(tried_path.read_text().split()) if tried_path.exists() else set()
    todo = [t for t in want if t not in wide.columns and t not in tried]
    print(f"prices: {len(want)} tickers, {len(todo)} to download")
    wait = pause
    while todo:
        part, todo = todo[:chunk], todo[chunk:]
        Catch.hit = False
        df = yf.download(part, start=start, auto_adjust=True, progress=False, threads=True)["Close"]
        if isinstance(df, pd.Series):
            df = df.to_frame(part[0])
        got = set(df.columns[df.notna().any()])
        limited = (set(part) - got) if Catch.hit else set()  # can't tell which failed for which reason
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df.drop(columns=[c for c in limited if c in df.columns]).dropna(axis=1, how="all")
        if len(df.columns):
            wide = df if wide.empty else wide.join(df, how="outer")
        tried |= set(part) - limited
        if limited:  # put them back and slow down
            todo = sorted(limited) + todo
            wait = min(wait * 2, 300)
            print(f"  rate limited on {len(limited)}; waiting {wait:.0f}s")
        else:
            wait = pause
        wide.to_parquet(path)
        tried_path.write_text("\n".join(sorted(tried)))
        print(f"  {len(todo)} left, {wide.shape[1]} with prices")
        time.sleep(wait)
    return wide


def load_prices() -> pd.DataFrame:
    path = DIR / "prices.parquet"
    if not path.exists():
        raise SystemExit("No congress prices yet. Run: alternative-signals congress-fetch")
    return pd.read_parquet(path)


# ---- industry codes, for the halal variant -----------------------------------------------------

# SEC SIC codes whose main business is generally impermissible: finance and insurance (interest),
# alcohol, tobacco, casinos and gambling, ammunition and weapons. Pork and adult content can't be
# read from SIC codes. This is a rough first pass, not a ruling.
HARAM_SIC = [(6000, 6799), (2082, 2085), (2100, 2199), (5813, 5813), (7990, 7999), (3480, 3489)]


def permissible_sic(sic: float) -> bool:
    if sic != sic:  # unknown (funds, delisted companies)
        return False
    return not any(lo <= sic <= hi for lo, hi in HARAM_SIC)


def fetch_sic(tickers: list[str], pause: float = 0.12) -> pd.DataFrame:
    """SIC industry code for each ticker that SEC still lists (cached)."""
    from .financials import _headers

    path = DIR / "sic.parquet"
    have = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=["ticker", "cik", "sic", "industry", "fy_end_month"])
    todo = sorted(set(tickers) - set(have["ticker"]))
    if not todo:
        return have
    r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=_headers(), timeout=30)
    r.raise_for_status()
    ciks = {row["ticker"].upper().replace(".", "-"): int(row["cik_str"]) for row in r.json().values()}
    print(f"industry codes: {len(todo)} tickers to look up, {sum(t in ciks for t in todo)} listed at SEC")
    rows = []
    for n, t in enumerate(todo, 1):
        cik = ciks.get(t)
        sic, industry, fy_end = np.nan, "", 12
        if cik:
            try:
                s = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
                                 headers=_headers(), timeout=30)
                s.raise_for_status()
                j = s.json()
                sic, industry = float(j.get("sic") or np.nan), j.get("sicDescription") or ""
                fy_end = int((j.get("fiscalYearEnd") or "1231")[:2])
            except Exception as e:
                print(f"  {t}: {e}")
            time.sleep(pause)
        rows.append({"ticker": t, "cik": cik, "sic": sic, "industry": industry, "fy_end_month": fy_end})
        if n % 250 == 0:
            print(f"  {n}/{len(todo)}")
            pd.concat([have, pd.DataFrame(rows)], ignore_index=True).to_parquet(path, index=False)
    have = pd.concat([have, pd.DataFrame(rows)], ignore_index=True)
    have.to_parquet(path, index=False)
    return have
