"""HTML page for the copy-the-politicians backtest."""

import html
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import congress, copytrade
from .config import REPORTS

COLORS = {"top": "#2a6fdb", "all": "#8a8986", "bottom": "#d9622b", "SPY": "#1f1f1f", "QQQ": "#7b4fd6"}
NAMES = {"top": "Copy the top members", "all": "Copy every member", "bottom": "Copy the bottom members"}


def growth_figure(s: copytrade.Setup) -> go.Figure:
    trades, px = congress.load_trades(), congress.load_prices()
    ev = copytrade.events(copytrade.buys(trades, options=s.options), px, s.horizon)
    fig = go.Figure()
    start = None
    for g in ("top", "all", "bottom"):
        port = copytrade.portfolio(copytrade.copied(ev, s, g), px)
        port = port[port.index >= pd.Timestamp(s.first_year, 1, 1)]
        start = port.index[0] if start is None else min(start, port.index[0])
        fig.add_scatter(x=port.index, y=(1 + port).cumprod(), name=NAMES[g], line=dict(color=COLORS[g], width=2))
    for b in ("SPY", "QQQ"):
        r = px[b].pct_change()
        r = r[r.index >= start]
        fig.add_scatter(x=r.index, y=(1 + r).cumprod(), name=b, line=dict(color=COLORS[b], width=1.5, dash="dot"))
    fig.update_layout(template="plotly_white", height=420, margin=dict(l=50, r=20, t=30, b=40),
                      font=dict(family="system-ui, sans-serif", size=12), hovermode="x unified",
                      yaxis=dict(title="Growth of $1", type="log"), legend=dict(orientation="h", y=-0.15))
    return fig


def _pct(v, signed=True):
    return "–" if v is None or (isinstance(v, float) and np.isnan(v)) else (f"{v:+.1%}" if signed else f"{v:.0%}")


def results_table(results: pd.DataFrame) -> str:
    rows = []
    for r in results.itertuples():
        if not r.trades:
            continue
        rows.append(
            f"<tr><td>{html.escape(r.setup)}</td><td>{NAMES[r.group]}</td><td>{r.trades:,}</td><td>{r.members}</td>"
            f"<td>{_pct(r.alpha_spy)} <span class='muted'>(t {r.t_spy:.1f})</span></td>"
            f"<td><b>{_pct(r.alpha_qqq)}</b> <span class='muted'>(t {r.t_qqq:.1f})</span></td>"
            f"<td>{r.beta_qqq:.2f}</td><td>{_pct(r.per_trade_vs_spy)}</td><td>{_pct(r.from_trade_date_vs_spy)}</td></tr>")
    return ("<table><thead><tr><th>Setup</th><th>Who is copied</th><th>Trades</th><th>Members</th>"
            "<th>Alpha vs SPY per year</th><th>Alpha vs QQQ per year</th><th>Beta to QQQ</th>"
            "<th>Avg trade vs SPY, from disclosure</th><th>Same, if bought on the trade date</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


def coverage_table() -> str:
    cov = congress.coverage()
    trades = congress.load_trades()
    per_year = trades.groupby("year").size()
    rows = "".join(f"<tr><td>{y}</td><td>{int(r.reports):,}</td><td>{int(r.electronic):,} "
                   f"({r.electronic / r.reports:.0%})</td><td>{int(per_year.get(y, 0)):,}</td><td>{int(r.members)}</td></tr>"
                   for y, r in cov.iterrows() if r.reports > 20)
    return ("<table><thead><tr><th>Year filed</th><th>Reports</th><th>Read (electronic)</th>"
            f"<th>Transactions parsed</th><th>Members filing</th></tr></thead><tbody>{rows}</tbody></table>")


def current_picks(s: copytrade.Setup) -> str:
    trades, px = congress.load_trades(), congress.load_prices()
    ev = copytrade.events(copytrade.buys(trades, options=s.options), px, s.horizon)
    year = date.today().year
    score = copytrade.ranking(ev, year, s)
    rows = "".join(f"<tr><td>{html.escape(m)}</td><td>{_pct(r['past_vs_spy'])}</td><td>{int(r['past_trades'])}</td></tr>"
                   for m, r in score.iterrows())
    return (f"<p class='muted'>Members the main setup copies in {year}, ranked on trades disclosed in "
            f"{year - s.lookback}–{year - 1} whose six-month hold had ended by January 1.</p>"
            "<table><thead><tr><th>Member</th><th>Avg past trade vs SPY</th><th>Past trades</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>")


def delay_text() -> str:
    t = congress.load_trades()
    d = t["delay"].dropna()
    d = d[(d >= 0) & (d < 2000)]
    return (f"Median gap between a trade and its report: <b>{d.median():.0f} days</b>; "
            f"{(d > 45).mean():.0%} of trades were reported later than the 45 days the STOCK Act allows.")


def verdict(results: pd.DataFrame) -> str:
    main = results[results["setup"].str.startswith("main")].set_index("group")
    if "top" not in main.index or not main.loc["top", "trades"]:
        return "Not enough data."
    top, every, bottom = main.loc["top"], main.loc["all"], main.loc["bottom"]
    tops = results[(results["group"] == "top") & (results["trades"] > 0)].set_index("setup")
    alls = results[results["group"] == "all"].set_index("setup").reindex(tops.index)
    better = int((tops["alpha_qqq"] > alls["alpha_qqq"]).sum())
    if top["t_qqq"] >= 2 and top["alpha_qqq"] > every["alpha_qqq"]:
        lead = "Copying the top members beat QQQ after their reporting delay, and the gap is unlikely to be luck."
    else:
        lead = ("Copying the members with the best past record did not work: they did no better than copying "
                "everyone, and no group beat the market by more than luck would explain.")
    return (f"{lead} Main setup, alpha a year vs QQQ: top members {top['alpha_qqq']:+.1%} (t {top['t_qqq']:.1f}), "
            f"every member {every['alpha_qqq']:+.1%} (t {every['t_qqq']:.1f}), bottom members "
            f"{bottom['alpha_qqq']:+.1%} (t {bottom['t_qqq']:.1f}). The top group beat the all-members group in "
            f"{better} of {len(tops)} setups.")


def write(results: pd.DataFrame) -> str:
    s = copytrade.Setup()
    fig = growth_figure(s).to_html(full_html=False, include_plotlyjs="cdn")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Copying Congress</title>
<style>
  :root {{ --bg:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --line:#e4e3df; --card:#fff; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#141413; --ink:#f2f1ee; --ink2:#a9a8a3; --line:#2e2d2a; --card:#1c1b19; }} }}
  body {{ background:var(--bg); color:var(--ink); font:15px/1.5 system-ui,sans-serif; margin:0; }}
  main {{ max-width:1100px; margin:0 auto; padding:24px 16px 64px; }}
  h1 {{ font-size:26px; margin:0 0 4px; }} h2 {{ font-size:19px; margin:32px 0 8px; }}
  .muted {{ color:var(--ink2); }} .lead {{ font-size:17px; }}
  .wrap {{ overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:8px; margin:8px 0; }}
  .plot {{ background:#fff; border-radius:8px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums; }}
  th, td {{ text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ font-weight:600; }}
</style></head><body><main>
<h1>Copying Congress</h1>
<p class="muted">Generated {date.today():%Y-%m-%d}. House periodic transaction reports (STOCK Act), Yahoo Finance prices.
Research only, not investment advice.</p>
<p class="lead">{html.escape(verdict(results))}</p>
<h2>How the test works</h2>
<ul>
<li>Each year, rank House members by how their disclosed stock buys did against SPY over the previous
{s.lookback} years, using only trades whose {s.horizon}-trading-day hold had finished before the year began.
Copy the top {s.top} (at least {s.min_trades} past trades each).</li>
<li>Buy each of their purchases at the close of the first trading day <i>after</i> the report was filed, and hold
for {s.horizon} trading days (about six months). Call-option buys are copied as the stock.</li>
<li>Daily returns of the resulting portfolio are compared with SPY and with QQQ. Alpha is the yearly return left
after allowing for how much the portfolio moves with the benchmark (beta). t above about 2 is unlikely to be luck.</li>
<li>"Every member" and "bottom members" are the same rule applied to everyone and to the worst-ranked, as checks.</li>
</ul>
<h2>Growth of $1, main setup</h2>
<div class="plot">{fig}</div>
<h2>Results</h2>
<div class="wrap">{results_table(results)}</div>
<p class="muted">The last two columns are average six-month returns per copied trade minus SPY. The difference
between them is what the reporting delay cost.</p>
<h2>Who would be copied now</h2>
<div class="wrap">{current_picks(s)}</div>
<h2>Data</h2>
<p>{delay_text()}</p>
<div class="wrap">{coverage_table()}</div>
<h2>Limits</h2>
<ul>
<li>Only House reports filed electronically are read. Paper reports are scanned images (most reports before
2018, about 13% now), so members who file on paper, including some heavy traders, are partly or fully missing.
The Senate isn't included yet.</li>
<li>Stocks no longer listed have no free price history and are dropped, which flatters every group a little.</li>
<li>Amounts are ranges, so every trade gets equal weight; members' real positions differ a lot in size.</li>
<li>The halal variant keeps shares in permissible industries by SEC industry code. It does not apply the debt and
cash ratio screen at the time of each trade.</li>
</ul>
</main></body></html>"""
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "congress.html"
    path.write_text(page, encoding="utf-8")
    return str(path)
