"""Step 3 of the sector rotation research: alt-data signals by industry.

- Insider buying: every open-market purchase (code P) and sale (code S) by officers and directors on Form 4,
  from SEC's quarterly bulk data sets (2006 on). Each month, per industry: (insiders buying - insiders
  selling) / (buying + selling), counting each insider-company pair once, by filing date.
- Congress buying: the same ratio for House members' disclosed buys and sells (2014 on), by filing date.

Companies are placed in Ken French's 12 industries by their SEC industry (SIC) code, so the signals line up
with the industry returns used in steps 1 and 2. Industries are ranked on the signal (as is, or relative to the
industry's own past 3 years, since tech insiders always sell more than utility insiders), and the top ones
are held for a month, exactly as in step 1.
"""

import io
import time
import zipfile
from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

from . import congress, rotation
from .config import DATA

DIR = DATA / "insiders_bulk"
SEC_BULK = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{}_form345.zip"
FRENCH_SIC = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Siccodes12.zip"


# ---- industries ---------------------------------------------------------------------------------

def parse_sic_ranges(text: str) -> list[tuple[str, int, int]]:
    """(industry, low, high) SIC ranges from Ken French's SiccodesNN.txt."""
    out, current = [], None
    for ln in text.splitlines():
        parts = ln.split()
        if len(parts) >= 2 and parts[0].isdigit() and not "-" in parts[0]:
            current = parts[1]
        elif parts and "-" in parts[0] and current:
            lo, hi = parts[0].split("-")
            out.append((current, int(lo), int(hi)))
    return out


def sic_ranges() -> list[tuple[str, int, int]]:
    path = DATA / "sectors" / "siccodes12.txt"
    if not path.exists():
        r = congress._get(FRENCH_SIC, headers=congress.HEADERS)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(z.read(z.namelist()[0]).decode("latin-1"))
    return parse_sic_ranges(path.read_text())


def industry(sic: float, ranges: list[tuple[str, int, int]]) -> str | None:
    """Ken French 12-industry code for a SIC code ('Other' if no range matches; None if SIC unknown)."""
    if sic != sic or sic is None:
        return None
    for name, lo, hi in ranges:
        if lo <= sic <= hi:
            return name
    return "Other"


# ---- insider data -------------------------------------------------------------------------------

def quarters(first: str = "2006Q1") -> list[str]:
    last = pd.Timestamp.today().to_period("Q") - 1
    return [f"{p.year}q{p.quarter}" for p in pd.period_range(first, last, freq="Q")]


def parse_quarter(z: zipfile.ZipFile) -> pd.DataFrame:
    """Open-market buys and sells by officers and directors in one quarterly data set."""
    def read(name, cols):
        with z.open(name) as f:
            return pd.read_csv(f, sep="\t", dtype=str, usecols=cols, quoting=3, on_bad_lines="skip")

    sub = read("SUBMISSION.tsv", ["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERCIK", "ISSUERTRADINGSYMBOL"])
    tr = read("NONDERIV_TRANS.tsv", ["ACCESSION_NUMBER", "TRANS_DATE", "TRANS_CODE", "TRANS_SHARES", "TRANS_PRICEPERSHARE"])
    own = read("REPORTINGOWNER.tsv", ["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNER_RELATIONSHIP"])
    sub = sub[sub["DOCUMENT_TYPE"] == "4"]
    tr = tr[tr["TRANS_CODE"].isin(["P", "S"])]
    own = own[own["RPTOWNER_RELATIONSHIP"].fillna("").str.contains("Director|Officer", case=False)]
    df = tr.merge(sub, on="ACCESSION_NUMBER").merge(own, on="ACCESSION_NUMBER")
    out = pd.DataFrame({
        "filed": pd.to_datetime(df["FILING_DATE"], format="%d-%b-%Y", errors="coerce"),
        "tx_date": pd.to_datetime(df["TRANS_DATE"], format="%d-%b-%Y", errors="coerce"),
        "issuer_cik": pd.to_numeric(df["ISSUERCIK"], errors="coerce"),
        "symbol": df["ISSUERTRADINGSYMBOL"].str.upper(),
        "owner": df["RPTOWNERCIK"],
        "code": df["TRANS_CODE"],
        "value": pd.to_numeric(df["TRANS_SHARES"], errors="coerce") * pd.to_numeric(df["TRANS_PRICEPERSHARE"], errors="coerce"),
    })
    return out.dropna(subset=["filed", "issuer_cik"])


def fetch_insiders(pause: float = 0.5) -> pd.DataFrame:
    from .financials import _headers

    DIR.mkdir(parents=True, exist_ok=True)
    for q in quarters():
        path = DIR / f"{q}.parquet"
        if path.exists():
            continue
        try:
            r = congress._get(SEC_BULK.format(q), headers=_headers())
        except Exception as e:
            print(f"{q}: {e}")
            continue
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            df = parse_quarter(z)
        df.to_parquet(path, index=False)
        print(f"{q}: {len(df):,} open-market trades by officers and directors")
        time.sleep(pause)
    return load_insiders()


def load_insiders() -> pd.DataFrame:
    files = sorted(DIR.glob("*.parquet"))
    if not files:
        raise SystemExit("No bulk insider data yet. Run: review-pulse sectors-fetch")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def fetch_cik_sic(ciks: list[int], pause: float = 0.11) -> pd.DataFrame:
    """SIC code for each company CIK, from SEC's submissions API (cached)."""
    from .financials import _headers

    path = DATA / "sectors" / "cik_sic.parquet"
    have = pd.read_parquet(path) if path.exists() else pd.DataFrame({"cik": pd.Series(dtype=int), "sic": pd.Series(dtype=float)})
    todo = sorted(set(int(c) for c in ciks) - set(have["cik"]))
    print(f"industry codes: {len(todo)} companies to look up")
    rows = []
    for n, cik in enumerate(todo, 1):
        sic = np.nan
        try:
            j = congress._get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=_headers(), tries=3).json()
            sic = float(j.get("sic") or np.nan)
        except Exception:
            pass
        rows.append({"cik": cik, "sic": sic})
        time.sleep(pause)
        if n % 500 == 0 or n == len(todo):
            have = pd.concat([have, pd.DataFrame(rows)], ignore_index=True)
            have.to_parquet(path, index=False)
            rows = []
            print(f"  {n}/{len(todo)}")
    return have


# ---- signals ------------------------------------------------------------------------------------

def monthly_counts(trades: pd.DataFrame, who: str, what: str, sector: pd.Series, code_col: str,
                   buy: str, sell: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Distinct (person, company) pairs buying and selling per industry per filing month."""
    t = trades.assign(industry=trades[what].map(sector)).dropna(subset=["industry"])
    t["month"] = t["filed"] + pd.offsets.MonthEnd(0)
    pairs = t.drop_duplicates(["month", who, what, code_col])
    counts = pairs.groupby(["month", "industry", code_col]).size().unstack(code_col, fill_value=0)
    b = counts.get(buy, pd.Series(0, index=counts.index)).unstack("industry", fill_value=0)
    s = counts.get(sell, pd.Series(0, index=counts.index)).unstack("industry", fill_value=0)
    idx = pd.date_range(min(b.index.min(), s.index.min()), max(b.index.max(), s.index.max()), freq="ME")
    cols = sorted(set(b.columns) | set(s.columns))
    return b.reindex(index=idx, columns=cols, fill_value=0), s.reindex(index=idx, columns=cols, fill_value=0)


def net_ratio(buys: pd.DataFrame, sells: pd.DataFrame, window: int, relative: bool) -> pd.DataFrame:
    """(buying - selling) / (buying + selling) over the past `window` months; 0 when nobody traded.
    `relative` subtracts the industry's own average over the previous 36 months."""
    b = buys.rolling(window, min_periods=window).sum()
    s = sells.rolling(window, min_periods=window).sum()
    r = ((b - s) / (b + s)).where((b + s) > 0, 0.0).where(b.notna())
    if relative:
        r = r - r.shift(window).rolling(36, min_periods=24).mean()
    return r


@dataclass(frozen=True)
class AltRule:
    source: str          # insiders | congress
    window: int = 3
    relative: bool = False
    k: int = 3

    @property
    def label(self) -> str:
        return (f"{self.source} net buying, {self.window}m" + (", vs own 3-year average" if self.relative else "")
                + f", top {self.k}")


SPLITS = {"insiders": (("2006-01-01", "2015-12-31"), ("2016-01-01", None)),
          "congress": (("2014-01-01", "2019-12-31"), ("2020-01-01", None))}


def evaluate(rets: pd.DataFrame, rf: pd.Series, counts: dict[str, tuple[pd.DataFrame, pd.DataFrame]],
             cost: float = 0.001) -> pd.DataFrame:
    """Every rule's results in and out of sample; `chosen` marks each source's best in-sample rule."""
    rows = []
    for source, (buys, sells) in counts.items():
        (i0, i1), (o0, o1) = SPLITS[source]
        windows = (1, 3, 6) if source == "insiders" else (3, 6, 12)
        for window, relative, k in product(windows, (False, True), (2, 3, 4)):
            rule = AltRule(source, window, relative, k)
            sig = net_ratio(buys, sells, window, relative).reindex(rets.index).reindex(columns=rets.columns)
            bt = rotation.backtest_weights(rets.loc[i0:], rotation.weights(sig.loc[i0:], k), cost)
            ins = rotation.stats(bt, rf, start=i0, end=i1)
            oos = rotation.stats(bt, rf, start=o0, end=o1)
            rows.append({"rule": rule, "label": rule.label, "source": source,
                         **{f"in_{k_}": v for k_, v in ins.items()}, **{f"out_{k_}": v for k_, v in oos.items()}})
    df = pd.DataFrame(rows)
    best = df.loc[df.groupby("source")["in_t_alpha"].idxmax()]
    df["chosen"] = df.index.isin(best.index)
    return df


def insider_counts() -> tuple[pd.DataFrame, pd.DataFrame]:
    ins = load_insiders()
    sic = pd.read_parquet(DATA / "sectors" / "cik_sic.parquet")
    ranges = sic_ranges()
    sector = pd.Series({int(c): industry(s, ranges) for c, s in zip(sic["cik"], sic["sic"])}).dropna()
    return monthly_counts(ins, "owner", "issuer_cik", sector, "code", "P", "S")


def congress_counts() -> tuple[pd.DataFrame, pd.DataFrame]:
    t = congress.load_trades()
    t = t[t["tx"].isin(["P", "S"]) & t["ticker"].notna()].copy()
    t["ticker"] = t["ticker"].map(congress.yahoo_symbol)
    sic = congress.fetch_sic(sorted(t["ticker"].unique()))
    ranges = sic_ranges()
    sector = pd.Series({tk: industry(s, ranges) for tk, s in zip(sic["ticker"], sic["sic"])}).dropna()
    return monthly_counts(t, "member", "ticker", sector, "tx", "P", "S")
