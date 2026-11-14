"""Monthly sector returns for the rotation research.

- Ken French data library: value-weighted monthly returns of 12 (or 49) US industry portfolios from 1926,
  plus the market and the 1-month T-bill rate. Long enough to separate skill from luck.
- SPDR sector ETFs: the funds you could actually trade, monthly from 1999.

All returns are simple monthly returns as decimals, indexed by month-end date.
"""

import io
import zipfile

import numpy as np
import pandas as pd
import requests

from .config import DATA

DIR = DATA / "sectors"
FRENCH = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/{}_CSV.zip"
HEADERS = {"User-Agent": "review-pulse/0.1 (research script)"}

# The 11 SPDR sector funds (real estate from Oct 2015, communication services from Jun 2018).
ETFS = {"XLB": "Materials", "XLE": "Energy", "XLF": "Financials", "XLI": "Industrials", "XLK": "Technology",
        "XLP": "Consumer staples", "XLU": "Utilities", "XLV": "Health care", "XLY": "Consumer discretionary",
        "XLRE": "Real estate", "XLC": "Communication services"}

INDUSTRY_NAMES = {"NoDur": "Consumer non-durables", "Durbl": "Consumer durables", "Manuf": "Manufacturing",
                  "Enrgy": "Energy", "Chems": "Chemicals", "BusEq": "Business equipment (tech)",
                  "Telcm": "Telecom", "Utils": "Utilities", "Shops": "Retail and services", "Hlth": "Health care",
                  "Money": "Finance", "Other": "Other"}


def parse_french(text: str) -> pd.DataFrame:
    """First monthly table in a Ken French CSV (value-weighted returns for the industry files)."""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(","))
    cols = [c.strip() for c in lines[start].split(",")[1:]]
    rows = []
    for ln in lines[start + 1:]:
        parts = [p.strip() for p in ln.split(",")]
        if len(parts[0]) != 6 or not parts[0].isdigit():
            break
        rows.append([parts[0]] + [float(p) for p in parts[1:]])
    df = pd.DataFrame(rows, columns=["month"] + cols)
    df.index = pd.to_datetime(df.pop("month"), format="%Y%m") + pd.offsets.MonthEnd(0)
    df.index.name = None
    df = df.mask(df <= -99.99) / 100
    return df


def _french(name: str) -> pd.DataFrame:
    DIR.mkdir(parents=True, exist_ok=True)
    path = DIR / f"{name}.parquet"
    if path.exists() and pd.Timestamp(path.stat().st_mtime, unit="s") > pd.Timestamp.now() - pd.Timedelta(days=30):
        return pd.read_parquet(path)
    r = requests.get(FRENCH.format(name), headers=HEADERS, timeout=60)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        text = z.read(z.namelist()[0]).decode("latin-1")
    df = parse_french(text)
    df.to_parquet(path)
    return df


def industries(n: int = 12) -> pd.DataFrame:
    """Monthly value-weighted returns of Ken French's n-industry portfolios (n = 12 or 49)."""
    return _french(f"{n}_Industry_Portfolios")


def factors() -> pd.DataFrame:
    """Monthly market excess return (Mkt-RF) and risk-free rate (RF); 'Mkt' is the market's total return."""
    f = _french("F-F_Research_Data_Factors")
    f["Mkt"] = f["Mkt-RF"] + f["RF"]
    return f


def etfs() -> pd.DataFrame:
    """Monthly total returns of the SPDR sector funds and SPY (from their first full month)."""
    DIR.mkdir(parents=True, exist_ok=True)
    path = DIR / "etfs.parquet"
    if path.exists() and pd.Timestamp(path.stat().st_mtime, unit="s") > pd.Timestamp.now() - pd.Timedelta(days=1):
        return pd.read_parquet(path)
    import yfinance as yf

    px = yf.download(list(ETFS) + ["SPY"], start="1998-12-01", auto_adjust=True, progress=False)["Close"]
    if px.empty or px.notna().sum().min() == 0:
        raise SystemExit("Yahoo Finance returned no ETF prices (possibly rate limited); try again later.")
    px.index = pd.to_datetime(px.index).tz_localize(None)
    monthly = px.resample("ME").last()
    rets = monthly.pct_change()
    # Drop the current, unfinished month.
    if monthly.index[-1] > px.index[-1] + pd.Timedelta(days=3):
        rets = rets.iloc[:-1]
    rets = rets.iloc[1:]
    rets.to_parquet(path)
    return rets


def risk_free() -> pd.Series:
    return factors()["RF"]


def fill_rf(rf: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """T-bill rate on `index`, carrying the last known rate forward past the end of the French data."""
    return rf.reindex(index).ffill().fillna(float(np.nan_to_num(rf.iloc[-1])))
