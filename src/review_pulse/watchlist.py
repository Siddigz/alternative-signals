"""Watchlist: each company's halal screen and the latest reading of every signal that runs to today.

Signals are shown against the company's own history (where the latest quarter ranks among all its
quarters), since the backtests compare each company with itself. A signal's column header says whether
it passed the backtest: q < 0.05 pooled across companies and the same sign in every robustness split.
"""

import html
import time
from datetime import date

import numpy as np
import pandas as pd

from . import analysis, earnings, filings, halal, insiders, prices, short_interest, trends, wiki
from .config import REPORTS, Company
from .quarters import label

LIVE = {  # signal name in analysis.SIGNALS: (quarterly function, column)
    "wikipedia": (wiki.quarterly, "wiki_yoy"),
    "google search": (trends.quarterly, "trends_yoy"),
    "filing words": (filings.quarterly, "filing_chg"),
    "insider buying": (insiders.quarterly, "insider_npr"),
    "short interest": (short_interest.quarterly, "short_dtc"),
}


def signal_status(panel: pd.DataFrame, results: pd.DataFrame) -> dict[str, str]:
    """'passed' / 'no evidence' per live signal, from the pooled results and robustness splits."""
    out = {}
    pooled = results[results["scope"] == "All companies"]
    for name in LIVE:
        rows = pooled[(pooled["signal"] == name) & (pooled["q_value"] < 0.05) & (pooled["rho"] > 0)]
        ok = False
        for r in rows.itertuples():
            rb = analysis.robustness(panel, name, r.outcome)
            splits = rb[rb["perm_p"].notna()]
            if len(splits) and (splits["rho"] > 0).all():
                ok = True
        out[name] = "passed backtest" if ok else "no evidence yet"
    return out


def latest_reading(company: Company, name: str) -> dict:
    fn, col = LIVE[name]
    q = fn(company)
    q = q.dropna(subset=[col]) if col in q else q.iloc[0:0]
    if q.empty:
        return {"value": np.nan, "quarter": "", "pct": np.nan}
    q = q.sort_values("qidx")
    v = float(q[col].iloc[-1])
    pct = float((q[col] < v).mean() + 0.5 * (q[col] == v).mean())  # ties count half
    fy, fq = divmod(int(q["qidx"].iloc[-1]), 4)
    return {"value": v, "quarter": label(fy, fq + 1), "pct": pct}


def _fmt(name: str, v: float) -> str:
    if np.isnan(v):
        return "–"
    if name in ("wikipedia", "google search"):
        return f"{np.expm1(v):+.0%} vs year ago"
    if name == "filing words":
        return f"{v:+.1f} per 1,000 words"
    if name == "insider buying":
        return f"{v:+.2f} net buying"
    return f"{v:.1f} days to cover"


def _rank(name: str, pct: float) -> str:
    if np.isnan(pct):
        return ""
    sign = analysis.SIGNALS[name][1]
    good = pct if sign > 0 else 1 - pct
    word = "high" if pct >= 0.8 else "low" if pct <= 0.2 else "usual"
    tone = "good" if good >= 0.8 else "bad" if good <= 0.2 else "mid"
    return f'<span class="rank {tone}">{word} for this company</span>'


def rows(companies: list[Company]) -> list[dict]:
    out = []
    for c in companies:
        row = {"company": c}
        try:
            row["screen"] = halal.screen(c)
        except (SystemExit, Exception) as e:
            row["screen"], row["screen_error"] = None, str(e)
        time.sleep(0.15)
        for name in LIVE:
            row[name] = latest_reading(c, name)
        try:
            e = earnings.quarterly(c, prices.load(c.ticker), prices.load(prices.MARKET))
            row["earnings"] = e.sort_values("earn_date").iloc[-1] if len(e) else None
        except SystemExit:
            row["earnings"] = None
        out.append(row)
    return out


def write(companies: list[Company], panel: pd.DataFrame, results: pd.DataFrame) -> str:
    status = signal_status(panel, results)
    data = rows(companies)
    order = {"passes": 0, "passes ratios; business not reviewed": 1, "unknown": 2, "fails": 3}
    data.sort(key=lambda r: (order.get(r["screen"].status if r["screen"] else "unknown", 2), r["company"].ticker))

    head = "".join(f"<th>{html.escape(n.capitalize())}<br><span class='muted small'>{status[n]}</span></th>"
                   for n in LIVE)
    body = []
    for r in data:
        c, s = r["company"], r["screen"]
        if s:
            cls = {"passes": "pass", "fails": "fail"}.get(s.status, "pending")
            why = "; ".join(s.reasons())
            halal_cell = (f'<span class="badge {cls}">{html.escape(s.status)}</span>'
                          + (f"<div class='small'>{html.escape(why)}</div>" if why else "")
                          + f"<div class='small muted'>debt {s.debt_ratio:.0%} · cash {s.cash_ratio:.0%} · "
                            f"interest income {s.interest_income_share:.1%} · balance sheet {s.as_of}</div>"
                          + (f"<div class='small note'>{html.escape(s.note)}</div>" if s.note else ""))
        else:
            halal_cell = f"<span class='badge pending'>unknown</span><div class='small muted'>{html.escape(r.get('screen_error', ''))}</div>"
        cells = []
        for n in LIVE:
            x = r[n]
            cells.append(f"<td>{_fmt(n, x['value'])}<div class='small muted'>{x['quarter']}</div>{_rank(n, x['pct'])}</td>")
        e = r["earnings"]
        earn = (f"{e['earn_ret']:+.1%}<div class='small muted'>{pd.Timestamp(e['earn_date']):%Y-%m-%d}</div>"
                if e is not None else "–")
        body.append(f"<tr><td><b>{html.escape(c.name)}</b><div class='small muted'>{c.ticker}</div></td>"
                    f"<td>{halal_cell}</td>{''.join(cells)}<td>{earn}</td></tr>")

    passed = [n for n, v in status.items() if v == "passed backtest"]
    lead = ("No live signal has passed the backtest yet, so these readings are for reference, not for trading."
            if not passed else f"Signals that passed the backtest: {', '.join(passed)}.")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>review-pulse watchlist</title>
<style>
  :root {{ --bg:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --line:#e4e3df; --card:#fff;
          --pass:#1f7a3f; --pass-bg:#e7f4ec; --fail:#a3261d; --fail-bg:#fbeae8; --pend:#7a5b00; --pend-bg:#fbf3dc; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#141413; --ink:#f2f1ee; --ink2:#a9a8a3; --line:#2e2d2a; --card:#1c1b19;
          --pass:#7ed3a0; --pass-bg:#16301f; --fail:#f19a90; --fail-bg:#3a1a17; --pend:#e8c766; --pend-bg:#332a10; }} }}
  body {{ background:var(--bg); color:var(--ink); font:14px/1.45 system-ui,sans-serif; margin:0; }}
  main {{ max-width:1300px; margin:0 auto; padding:24px 16px 64px; }}
  h1 {{ font-size:24px; margin:0 0 4px; }} .muted {{ color:var(--ink2); }} .small {{ font-size:12px; }}
  .wrap {{ overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:8px; }}
  table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }}
  th, td {{ text-align:left; vertical-align:top; padding:8px 10px; border-bottom:1px solid var(--line); }}
  th {{ font-weight:600; position:sticky; top:0; background:var(--card); }}
  .badge {{ display:inline-block; padding:1px 8px; border-radius:999px; font-size:12px; font-weight:600; }}
  .pass {{ color:var(--pass); background:var(--pass-bg); }} .fail {{ color:var(--fail); background:var(--fail-bg); }}
  .pending {{ color:var(--pend); background:var(--pend-bg); }}
  .note {{ color:var(--pend); }}
  .rank {{ font-size:12px; }} .rank.good {{ color:var(--pass); }} .rank.bad {{ color:var(--fail); }} .rank.mid {{ color:var(--ink2); }}
</style></head><body><main>
<h1>Watchlist</h1>
<p class="muted">Generated {date.today():%Y-%m-%d}. {html.escape(lead)}</p>
<p class="muted small">Halal ratios follow AAOIFI Standard 21: interest-bearing debt and cash+securities each under 30% of
12-month average market value, interest income under 5% of revenue. The business-activity check is done by hand in
config/companies.yaml; until then a company shows "business not reviewed". Research aid only: confirm with a scholar
or screening service before investing. Not investment advice.</p>
<div class="wrap"><table>
<thead><tr><th>Company</th><th>Halal screen</th>{head}<th>Last earnings-day move</th></tr></thead>
<tbody>{''.join(body)}</tbody></table></div>
</main></body></html>"""
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "watchlist.html"
    path.write_text(page, encoding="utf-8")
    return str(path)
