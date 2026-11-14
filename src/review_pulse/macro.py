"""US business-cycle indicators from FRED, aligned to when they were actually known.

Each value is placed at the month-end when an investor could have used it:
- Treasury yields (GS10, TB3MS) are monthly averages known at month end: no lag.
- Unemployment (UNRATE), consumer prices (CPIAUCNS) and industrial production (INDPRO) for month m are
  published during month m+1, so they are used from the end of m+1.
FRED serves today's revised figures, not what was first published; revisions to these series are small,
but this flatters any macro signal slightly.
"""

import io

import pandas as pd

from .config import DATA
from .congress import _get

DIR = DATA / "sectors"
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
HEADERS: dict = {}  # FRED blocks Python requests with a custom client name but accepts the default one
SERIES = {"GS10": 0, "TB3MS": 0, "UNRATE": 1, "CPIAUCNS": 1, "INDPRO": 1}  # id: months of publication lag


def parse_fred(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text), na_values=".")
    s = pd.Series(df.iloc[:, 1].astype(float).to_numpy(),
                  index=pd.to_datetime(df.iloc[:, 0]) + pd.offsets.MonthEnd(0), name=df.columns[1])
    return s.dropna()


def series(sid: str) -> pd.Series:
    DIR.mkdir(parents=True, exist_ok=True)
    path = DIR / f"fred_{sid}.parquet"
    if path.exists() and pd.Timestamp(path.stat().st_mtime, unit="s") > pd.Timestamp.now() - pd.Timedelta(days=7):
        return pd.read_parquet(path)[sid]
    r = _get(URL.format(sid), headers=HEADERS)  # FRED drops connections now and then; retries with backoff
    s = parse_fred(r.text)
    s.to_frame().to_parquet(path)
    return s


def known(s: pd.Series, lag: int) -> pd.Series:
    """Shift a monthly series so each value sits at the month-end it became known."""
    out = s.copy()
    out.index = out.index + pd.offsets.MonthEnd(lag)
    return out


def indicators() -> pd.DataFrame:
    """Monthly indicators, each as known at that month-end.

    term:       10-year minus 3-month Treasury yield (percentage points); below 0 = inverted curve.
    inflation:  consumer prices vs a year earlier.
    production: industrial production vs a year earlier.
    unemp_gap:  3-month average unemployment rate minus its lowest 3-month average in the past 12 months
                (the Sahm rule; 0.5 or more has marked the start of every recession since 1970).
    """
    raw = {sid: known(series(sid), lag) for sid, lag in SERIES.items()}
    u3 = raw["UNRATE"].rolling(3).mean()
    df = pd.DataFrame({
        "term": raw["GS10"] - raw["TB3MS"],
        "inflation": raw["CPIAUCNS"].pct_change(12, fill_method=None),
        "production": raw["INDPRO"].pct_change(12, fill_method=None),
        "unemp_gap": u3 - u3.rolling(12).min(),
    })
    return df.sort_index()


def regimes(ind: pd.DataFrame) -> pd.DataFrame:
    """True where each slowdown warning is on."""
    return pd.DataFrame({
        "inverted curve": ind["term"] < 0,
        "rising unemployment": ind["unemp_gap"] >= 0.5,
        "falling production": ind["production"] < 0,
        "high inflation": ind["inflation"] > 0.05,
    }).where(ind.notna().all(axis=1))
