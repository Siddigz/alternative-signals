"""Daily check: new stock buys disclosed by the House members the backtest would copy, halal-screened.

Run `alternative-signals congress-alerts`. It downloads this year's new reports, picks out purchases filed in the
last few days, keeps those by this year's top-ranked members (the main backtest setup), and screens each
stock: business activity by SEC industry code, then the AAOIFI debt / cash / interest-income ratios.
Writes reports/congress_alerts.html and prints a short summary. Buys already shown on an earlier run are
marked as seen, so a scheduled run can say what's new.
"""

import html
from datetime import date

import numpy as np
import pandas as pd

from . import congress, copytrade, halal
from .config import REPORTS

SEEN = congress.DIR / "alerts_seen.txt"


def _key(r) -> str:
    return f"{r.member}|{r.ticker}|{pd.Timestamp(r.filed):%Y-%m-%d}"


def check(days: int = 7) -> dict:
    today = pd.Timestamp(date.today())
    years = [today.year - 1, today.year] if today.month == 1 else [today.year]
    trades = congress.fetch(years=years)
    s = copytrade.Setup()
    ev = copytrade.events(copytrade.buys(trades, options=s.options), congress.load_prices(), s.horizon)
    top = copytrade.ranking(ev, today.year, s)

    b = copytrade.buys(trades, options=True)
    recent = b[b["filed"] >= today - pd.Timedelta(days=days)].copy()
    picked = recent[recent["member"].isin(top.index)].copy()
    others = recent[~recent["member"].isin(top.index)]

    seen = set(SEEN.read_text().split("\n")) if SEEN.exists() else set()
    sic = congress.fetch_sic(sorted(picked["ticker"].unique())) if len(picked) else pd.DataFrame(
        columns=["ticker", "cik", "sic", "industry", "fy_end_month"])
    sic = sic.set_index("ticker")
    rows = []
    for r in picked.sort_values("filed", ascending=False).itertuples():
        row = {"member": r.member, "ticker": r.ticker, "filed": r.filed, "tx_date": r.tx_date,
               "option": bool(r.option), "amt_low": r.amt_low, "new": _key(r) not in seen,
               "past_vs_spy": top.loc[r.member, "past_vs_spy"], "industry": "", "status": "unknown",
               "why": "", "move_since_trade": np.nan, "move_since_filed": np.nan}
        info = sic.loc[r.ticker] if r.ticker in sic.index else None
        if info is None or pd.isna(info["cik"]):
            row["why"] = "not found at SEC (a fund, foreign listing or unlisted)"
        else:
            row["industry"] = info["industry"]
            if not congress.permissible_sic(info["sic"]):
                row["status"], row["why"] = "fails", f"business: {info['industry']}"
            else:
                try:
                    sc = halal.screen_ticker(r.ticker, int(info["cik"]), int(info["fy_end_month"] or 12))
                    row["status"] = "fails" if sc.financial_pass is False else (
                        "passes ratios; check business by hand" if sc.financial_pass else "unknown")
                    row["why"] = "; ".join(sc.reasons()) or (
                        f"debt {sc.debt_ratio:.0%}, cash {sc.cash_ratio:.0%}, interest income {sc.interest_income_share:.1%}")
                except (SystemExit, Exception) as e:
                    row["why"] = f"screen failed: {e}"
        try:
            from . import prices
            close = prices.download(r.ticker, (r.tx_date - pd.Timedelta(days=7)).strftime("%Y-%m-%d"),
                                    (today + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
            on = lambda d: close[close.index <= d].iloc[-1] if (close.index <= d).any() else close.iloc[0]
            row["move_since_trade"] = close.iloc[-1] / on(r.tx_date) - 1
            row["move_since_filed"] = close.iloc[-1] / on(r.filed) - 1
        except (SystemExit, Exception):
            pass
        if r.option:
            row["why"] = ("call option bought; options are generally not permissible, the stock is shown instead. "
                          + row["why"])
        rows.append(row)

    SEEN.write_text("\n".join(sorted(seen | {_key(r) for r in picked.itertuples()})))
    return {"rows": pd.DataFrame(rows), "top": top, "others": len(others), "days": days,
            "checked": today, "reports": int(trades[trades["filed"] >= today - pd.Timedelta(days=days)]["doc_id"].nunique())}


def _verdict() -> str:
    path = congress.DIR / "results.parquet"
    if not path.exists():
        return "The copy-trading backtest hasn't been run yet, so whether copying these members pays is unknown."
    from .congress_report import verdict
    return verdict(pd.read_parquet(path))


def write(res: dict) -> str:
    df = res["rows"]
    pct = lambda v: "–" if pd.isna(v) else f"{v:+.1%}"
    body = []
    for r in df.itertuples():
        cls = {"fails": "fail", "passes ratios; check business by hand": "pass"}.get(r.status, "pending")
        body.append(
            f"<tr><td>{'<span class=new>new</span> ' if r.new else ''}{pd.Timestamp(r.filed):%Y-%m-%d}</td>"
            f"<td>{html.escape(r.member)}<div class='small muted'>past trades {pct(r.past_vs_spy)} vs SPY</div></td>"
            f"<td><b>{html.escape(r.ticker)}</b><div class='small muted'>{html.escape(r.industry)}</div></td>"
            f"<td>{pd.Timestamp(r.tx_date):%Y-%m-%d}<div class='small muted'>{(r.filed - r.tx_date).days} days before filing</div></td>"
            f"<td>${r.amt_low:,.0f}+</td><td>{pct(r.move_since_trade)}</td><td>{pct(r.move_since_filed)}</td>"
            f"<td><span class='badge {cls}'>{html.escape(r.status)}</span><div class='small'>{html.escape(r.why)}</div></td></tr>")
    table = ("<p>No buys by the copied members in this window.</p>" if df.empty else
             "<div class='wrap'><table><thead><tr><th>Filed</th><th>Member</th><th>Stock</th><th>Traded</th>"
             "<th>Amount</th><th>Move since trade</th><th>Move since filing</th><th>Halal screen</th></tr></thead>"
             f"<tbody>{''.join(body)}</tbody></table></div>")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Congress buys</title>
<style>
  :root {{ --bg:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --line:#e4e3df; --card:#fff;
          --pass:#1f7a3f; --pass-bg:#e7f4ec; --fail:#a3261d; --fail-bg:#fbeae8; --pend:#7a5b00; --pend-bg:#fbf3dc; --new:#2a6fdb; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#141413; --ink:#f2f1ee; --ink2:#a9a8a3; --line:#2e2d2a; --card:#1c1b19;
          --pass:#7ed3a0; --pass-bg:#16301f; --fail:#f19a90; --fail-bg:#3a1a17; --pend:#e8c766; --pend-bg:#332a10; --new:#8fb6f5; }} }}
  body {{ background:var(--bg); color:var(--ink); font:14px/1.45 system-ui,sans-serif; margin:0; }}
  main {{ max-width:1100px; margin:0 auto; padding:24px 16px 64px; }}
  h1 {{ font-size:24px; margin:0 0 4px; }} .muted {{ color:var(--ink2); }} .small {{ font-size:12px; }}
  .wrap {{ overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:8px; }}
  table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }}
  th, td {{ text-align:left; vertical-align:top; padding:8px 10px; border-bottom:1px solid var(--line); }}
  .badge {{ display:inline-block; padding:1px 8px; border-radius:999px; font-size:12px; font-weight:600; }}
  .pass {{ color:var(--pass); background:var(--pass-bg); }} .fail {{ color:var(--fail); background:var(--fail-bg); }}
  .pending {{ color:var(--pend); background:var(--pend-bg); }}
  .new {{ color:var(--new); font-weight:700; font-size:12px; }}
</style></head><body><main>
<h1>Congress buys</h1>
<p class="muted">Checked {res['checked']:%Y-%m-%d}: {res['reports']} House reports filed in the last {res['days']} days.
Showing stock buys by the {len(res['top'])} members the backtest copies this year; {res['others']} buys by other
members are left out.</p>
<p><b>Backtest:</b> {html.escape(_verdict())}</p>
{table}
<p class="muted small">Halal screen: SEC industry code for the business, then AAOIFI ratios (debt and cash+securities under
30% of market value, interest income under 5% of revenue). Industry codes can't catch everything (pork, alcohol sold
alongside other goods), so check the business by hand. Research aid only, not investment advice or a ruling.</p>
</main></body></html>"""
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "congress_alerts.html"
    path.write_text(page, encoding="utf-8")
    return str(path)


def summary(res: dict) -> str:
    df = res["rows"]
    if df.empty:
        return f"No buys by the copied members in the last {res['days']} days."
    new = df[df["new"]]
    ok = new[new["status"].str.startswith("passes")]
    lines = [f"{len(new)} new buys by copied members ({len(df)} in the last {res['days']} days); "
             f"{len(ok)} of the new ones pass the halal ratios."]
    for r in new.itertuples():
        lines.append(f"  {r.ticker:6} {r.member} (filed {pd.Timestamp(r.filed):%Y-%m-%d}, traded "
                     f"{pd.Timestamp(r.tx_date):%Y-%m-%d}): {r.status}")
    return "\n".join(lines)
