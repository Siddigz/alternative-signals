"""Shariah screen for live use: financial ratios from SEC EDGAR plus a business-activity note.

Financial ratios follow AAOIFI Shariah Standard 21 (one common standard; others such as DJIM or MSCI use
total assets or a 24-36 month average market value instead):
  - interest-bearing debt                    < 30% of market value
  - cash + interest-bearing investments      < 30% of market value
  - interest (non-permissible) income        < 5% of revenue

Market value = shares outstanding x the average closing price over the last 12 months.
Balance-sheet items come from the latest 10-Q/10-K. Debt and cash concepts vary between companies, so the
components used are shown on the watchlist to check.

The business-activity screen (what the company sells) can't be computed. It is set by hand in
config/companies.yaml (`halal_business`, `halal_note`) and stays "not reviewed" until someone checks it.
This is a research aid, not a fatwa; confirm with a scholar or a screening service before investing.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import financials, prices
from .config import Company

DEBT_MAX, CASH_MAX, INCOME_MAX = 0.30, 0.30, 0.05

LONG_TERM_TOTAL = ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities", "DebtInstrumentCarryingAmount"]
LONG_TERM_NONCURRENT = ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"]
LONG_TERM_CURRENT = ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"]
SHORT_TERM = ["ShortTermBorrowings", "CommercialPaper", "LinesOfCreditCurrent"]
CASH = ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash"]
SECURITIES = ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"]
INTEREST_INCOME = ["InvestmentIncomeInterest", "InterestIncomeOther", "InvestmentIncomeInterestAndDividend",
                   "InterestAndOtherIncome"]


def instants(facts: dict, concept: str, taxonomy: str = "us-gaap", unit: str = "USD") -> pd.Series:
    """Point-in-time values for one concept, by period end date (summed when several share a date,
    as with share classes). Latest filing wins for each date."""
    rows = [e for e in facts.get("facts", {}).get(taxonomy, {}).get(concept, {}).get("units", {}).get(unit, [])
            if "start" not in e]
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows)
    df["end"] = pd.to_datetime(df["end"])
    df = df.sort_values("filed").drop_duplicates(["end", "frame"] if "frame" in df else ["end"], keep="last")
    return df.groupby("end")["val"].sum().astype(float)


def latest(facts: dict, concepts: list[str], on: pd.Timestamp | None = None, **kw) -> tuple[float, str] | None:
    """Value of the first concept that has one at `on` (or at its own latest date if `on` is None)."""
    for c in concepts:
        s = instants(facts, c, **kw)
        if s.empty:
            continue
        if on is None:
            return float(s.iloc[-1]), c
        near = s[(s.index >= on - pd.Timedelta(days=10)) & (s.index <= on + pd.Timedelta(days=10))]
        if len(near):
            return float(near.iloc[-1]), c
    return None


def shares_outstanding(facts: dict, on: pd.Timestamp) -> tuple[float, str] | None:
    """Cover-page share count, else the balance-sheet count, else the latest weighted average."""
    hit = latest(facts, ["EntityCommonStockSharesOutstanding"], taxonomy="dei", unit="shares")
    if hit:
        return hit
    hit = latest(facts, ["CommonStockSharesOutstanding"], on, unit="shares")
    if hit:
        return hit
    for c in ("WeightedAverageNumberOfSharesOutstandingBasic", "WeightedAverageNumberOfDilutedSharesOutstanding"):
        rows = facts.get("facts", {}).get("us-gaap", {}).get(c, {}).get("units", {}).get("shares", [])
        if rows:
            last = max(rows, key=lambda e: (e["end"], e["filed"]))
            return float(last["val"]), c
    return None


@dataclass
class Screen:
    ticker: str
    as_of: str
    market_value: float
    debt: float
    debt_parts: str
    cash: float
    cash_parts: str
    interest_income_share: float
    debt_ratio: float
    cash_ratio: float
    financial_pass: bool | None
    business: bool | None
    note: str

    @property
    def status(self) -> str:
        if self.financial_pass is False or self.business is False:
            return "fails"
        if self.financial_pass and self.business:
            return "passes"
        if self.financial_pass:
            return "passes ratios; business not reviewed"
        return "unknown"

    def reasons(self) -> list[str]:
        out = []
        if self.debt_ratio >= DEBT_MAX:
            out.append(f"debt {self.debt_ratio:.0%} of market value (limit 30%)")
        if self.cash_ratio >= CASH_MAX:
            out.append(f"cash and securities {self.cash_ratio:.0%} (limit 30%)")
        if self.interest_income_share >= INCOME_MAX:
            out.append(f"interest income {self.interest_income_share:.1%} of revenue (limit 5%)")
        if self.business is False:
            out.append("business activity")
        return out


def screen(company: Company, facts: dict | None = None, close: pd.Series | None = None,
           fin: pd.DataFrame | None = None) -> Screen:
    facts = facts or financials.company_facts(financials.company_cik(company))
    # Balance-sheet date: the latest date with a cash figure under any of the cash concepts
    # (companies switch concepts over the years).
    dates = [instants(facts, c).index.max() for c in CASH if not instants(facts, c).empty]
    if not dates:
        raise SystemExit(f"{company.ticker}: no balance sheet in EDGAR")
    on = max(dates)
    cash_val, cash_c = latest(facts, CASH, on)
    sec = latest(facts, SECURITIES, on)
    cash_parts = cash_c + (f" + {sec[1]}" if sec else "")
    cash = cash_val + (sec[0] if sec else 0.0)

    parts, debt = [], 0.0
    total = latest(facts, LONG_TERM_TOTAL, on)
    if total:
        debt += total[0]; parts.append(total[1])
    else:
        for group in (LONG_TERM_NONCURRENT, LONG_TERM_CURRENT):
            hit = latest(facts, group, on)
            if hit:
                debt += hit[0]; parts.append(hit[1])
    short = latest(facts, SHORT_TERM, on)
    if short:
        debt += short[0]; parts.append(short[1])

    shares = shares_outstanding(facts, on)
    try:
        close = prices.load(company.ticker) if close is None else close
        avg = float(close[close.index >= close.index[-1] - pd.DateOffset(months=12)].mean())
    except SystemExit:
        avg = np.nan
    mv = shares[0] * avg if shares else np.nan

    fin = (financials.load(company.ticker) if fin is None else fin).sort_values("qidx")
    rev_ttm = float(fin["revenue"].tail(4).sum())
    inc = financials.quarterly_series(facts, INTEREST_INCOME)
    inc_ttm = float(inc.sort_values("end")["val"].tail(4).sum()) if len(inc) else 0.0
    income_share = inc_ttm / rev_ttm if rev_ttm else np.nan

    debt_ratio, cash_ratio = debt / mv, cash / mv
    if np.isnan(mv):
        ok = None
    else:
        ok = bool(debt_ratio < DEBT_MAX and cash_ratio < CASH_MAX and not (income_share >= INCOME_MAX))
    return Screen(company.ticker, f"{on:%Y-%m-%d}", mv, debt, " + ".join(parts) or "none reported",
                  cash, cash_parts, income_share, debt_ratio, cash_ratio, ok,
                  company.halal_business, company.halal_note)


def screen_ticker(ticker: str, cik: int, fy_end_month: int = 12, business: bool | None = None,
                  note: str = "") -> Screen:
    """Screen any listed company by ticker (not just those in the config), using a year of fresh prices."""
    c = Company(ticker=ticker, name=ticker, fy_end_month=fy_end_month, stores=[], categories=[],
                cik=cik, halal_business=business, halal_note=note)
    facts = financials.company_facts(cik)
    fin = financials.from_facts(facts, c)
    end = pd.Timestamp.today()
    close = prices.download(ticker, (end - pd.DateOffset(months=13)).strftime("%Y-%m-%d"),
                            (end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    return screen(c, facts, close, fin)
