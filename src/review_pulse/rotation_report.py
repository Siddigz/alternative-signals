"""HTML page for the sector rotation research."""

import html
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import rotation, sectors
from .config import REPORTS

BLUE, GREY, INK, ORANGE = "#2a6fdb", "#8a8986", "#1f1f1f", "#d9622b"
LAYOUT = dict(template="plotly_white", font=dict(family="system-ui, sans-serif", size=12),
              margin=dict(l=55, r=20, t=30, b=40), legend=dict(orientation="h", y=-0.18))


def _p(v, signed=True):
    return "–" if v is None or (isinstance(v, float) and np.isnan(v)) else (f"{v:+.1%}" if signed else f"{v:.1%}")


def run() -> dict:
    rf = sectors.risk_free()
    res = {}
    for n in (12, 49):
        res[n] = rotation.choose(sectors.industries(n), rf, rotation.grid())
    chosen = res[12][res[12]["chosen"]].copy()
    chosen["p_out"] = chosen["out_t_alpha"].map(rotation.p_from_t)
    chosen["holm_out"] = rotation.holm(chosen["p_out"]).to_numpy()
    e = sectors.etfs()
    secs, rfe = e.drop(columns=["SPY"]), sectors.fill_rf(rf, e.index)
    etf_rows = []
    for rule in chosen["rule"]:
        s = rotation.stats(rotation.backtest(secs, rule), rfe, market=e["SPY"])
        etf_rows.append({"label": rule.label, **s})
    return {"grid12": res[12], "grid49": res[49], "chosen": chosen, "etf": pd.DataFrame(etf_rows), "rf": rf}


def verdict(r: dict) -> str:
    c = r["chosen"].set_index("signal")
    mom = c.loc["momentum"]
    etf = r["etf"].set_index("label").loc[mom["label"]]
    works = mom["holm_out"] < 0.05 and mom["out_alpha"] > 0
    late = rotation.stats(rotation.backtest(sectors.industries(12), mom["rule"]), r["rf"], start="1999-01-01")
    lead = ("Industry momentum held up out of sample: " if works else "Industry momentum did not hold up out of sample: ")
    return (lead + f"holding the 3 industries with the best past year beat holding all 12 by "
            f"{mom['out_active']:+.1%} a year from 1990 (alpha {mom['out_alpha']:+.1%}, t {mom['out_t_alpha']:.1f}), "
            f"using a rule chosen only on 1927–1989. It has been weaker since 1999 ({late['active']:+.1%} a year, "
            f"t {late['t_active']:.1f}), and the same rule on the sector ETFs you can actually buy added "
            f"{etf['alpha']:+.1%} a year since 1999 (t {etf['t_alpha']:.1f}), which could easily be luck. "
            f"Short-term reversal and low volatility did not beat holding every sector.")


def growth_figure(rule: rotation.Rule, rf: pd.Series) -> go.Figure:
    i12 = sectors.industries(12)
    bt = rotation.backtest(i12, rule)
    mkt = sectors.factors()["Mkt"].reindex(bt.index)
    fig = go.Figure()
    for col, name, color, dash in (("ret", f"Rotation: {rule.label}", BLUE, None), ("ew", "All 12 industries, equal weight", GREY, None)):
        fig.add_scatter(x=bt.index, y=(1 + bt[col]).cumprod(), name=name, line=dict(color=color, width=2, dash=dash))
    fig.add_scatter(x=bt.index, y=(1 + mkt).cumprod(), name="US market", line=dict(color=INK, width=1.2, dash="dot"))
    fig.add_vline(x=pd.Timestamp("1990-01-01").timestamp() * 1000, line=dict(color=ORANGE, dash="dash", width=1))
    fig.add_annotation(x=pd.Timestamp("1990-01-01"), y=1, yref="paper", text=" out-of-sample from here",
                       showarrow=False, xanchor="left", font=dict(color=ORANGE, size=11))
    fig.update_layout(**LAYOUT, height=420, yaxis=dict(title="Growth of $1 (log scale)", type="log"), hovermode="x unified")
    return fig


def decade_figure(rule: rotation.Rule) -> go.Figure:
    d = rotation.by_decade(rotation.backtest(sectors.industries(12), rule))
    fig = go.Figure(go.Bar(x=[f"{y}s" for y in d.index], y=d["active"],
                           marker_color=[BLUE if v >= 0 else ORANGE for v in d["active"]],
                           hovertemplate="%{x}: %{y:+.1%} a year<extra></extra>"))
    fig.update_layout(**LAYOUT, height=300, yaxis=dict(title="Yearly return vs all industries", tickformat="+.0%"),
                      showlegend=False)
    return fig


def chosen_table(r: dict) -> str:
    etf = r["etf"].set_index("label")
    rows = []
    for c in r["chosen"].itertuples():
        e = etf.loc[c.label]
        rows.append(
            f"<tr><td>{html.escape(c.label)}</td><td>{_p(c.in_active)} <span class=muted>(t {c.in_t_alpha:.1f})</span></td>"
            f"<td><b>{_p(c.out_active)}</b> <span class=muted>(t {c.out_t_alpha:.1f}, Holm p {c.holm_out:.3f})</span></td>"
            f"<td>{c.out_sharpe:.2f} <span class=muted>vs {c.out_ew_sharpe:.2f}</span></td>"
            f"<td>{_p(e['alpha'])} <span class=muted>(t {e['t_alpha']:.1f})</span></td>"
            f"<td>{_p(e['cagr'], False)} <span class=muted>vs {_p(e['ew_cagr'], False)} all / {_p(e.get('mkt_cagr'), False)} SPY</span></td>"
            f"<td>{c.out_turnover:.1f}×</td></tr>")
    return ("<table><thead><tr><th>Rule (best of its kind, 1927–1989)</th><th>1927–1989 vs all industries</th>"
            "<th>1990–2026 vs all industries</th><th>Sharpe 1990–2026</th><th>Sector ETFs 1999–2026: alpha</th>"
            "<th>ETFs: yearly return</th><th>Turnover a year</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>")


def grid_table(df: pd.DataFrame) -> str:
    d = df.sort_values(["signal", "out_t_alpha"], ascending=[True, False])
    rows = "".join(f"<tr><td>{html.escape(x.label)}{' ✓' if x.chosen else ''}</td><td>{_p(x.in_active)}</td>"
                   f"<td>{x.in_t_alpha:.1f}</td><td>{_p(x.out_active)}</td><td>{x.out_t_alpha:.1f}</td></tr>"
                   for x in d.itertuples())
    return ("<table><thead><tr><th>Rule</th><th>1927–89 vs all</th><th>t</th><th>1990–2026 vs all</th><th>t</th></tr>"
            f"</thead><tbody>{rows}</tbody></table>")


def write(r: dict) -> str:
    mom = r["chosen"].set_index("signal").loc["momentum", "rule"]
    g12, g49 = r["grid12"], r["grid49"]
    m12, m49 = g12[g12["signal"] == "momentum"], g49[g49["signal"] == "momentum"]
    growth = growth_figure(mom, r["rf"]).to_html(full_html=False, include_plotlyjs="cdn")
    decades = decade_figure(mom).to_html(full_html=False, include_plotlyjs=False)
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sector rotation</title>
<style>
  :root {{ --bg:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --line:#e4e3df; --card:#fff; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#141413; --ink:#f2f1ee; --ink2:#a9a8a3; --line:#2e2d2a; --card:#1c1b19; }} }}
  body {{ background:var(--bg); color:var(--ink); font:15px/1.5 system-ui,sans-serif; margin:0; }}
  main {{ max-width:1100px; margin:0 auto; padding:24px 16px 64px; }}
  h1 {{ font-size:26px; margin:0 0 4px; }} h2 {{ font-size:19px; margin:32px 0 8px; }}
  .muted {{ color:var(--ink2); }} .lead {{ font-size:17px; }}
  .wrap {{ overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:8px; margin:8px 0; }}
  .plot {{ background:#fff; border-radius:8px; margin:8px 0; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums; }}
  th, td {{ text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ font-weight:600; }} details {{ margin:8px 0; }}
</style></head><body><main>
<h1>Sector rotation</h1>
<p class="muted">Generated {date.today():%Y-%m-%d}. Ken French data library (US industries, 1926–2026), SPDR sector ETFs
(Yahoo Finance, 1999–2026). Research only, not investment advice.</p>
<p class="lead">{html.escape(verdict(r))}</p>
<h2>How the test works</h2>
<ul>
<li>At the end of each month, rank the sectors by a signal using only data up to that month, and hold the top ones in
equal weight the next month. Trading costs 0.10% of the amount bought or sold.</li>
<li>Rotation has to beat the simple alternative: holding every sector in equal weight. "Alpha" is the yearly return
left after allowing for how much the rotation moves with that benchmark. t above about 2 is unlikely to be luck.</li>
<li>Each signal's settings (look-back, skipping the latest month, how many sectors to hold) are chosen on 1927–1989
only. The chosen rule is then tested unchanged on 1990–2026 and on the sector ETFs. Holm-adjusted p-values allow for
testing three signals.</li>
<li>Signals: <b>momentum</b> (best past return), <b>reversal</b> (last month's losers), <b>low volatility</b>
(calmest sectors).</li>
</ul>
<h2>Results</h2>
<div class="wrap">{chosen_table(r)}</div>
<h2>Growth of $1, 12 industries</h2>
<div class="plot">{growth}</div>
<h2>Momentum by decade</h2>
<p class="muted">Yearly return of the momentum rule minus holding all 12 industries.</p>
<div class="plot">{decades}</div>
<h2>Every setting tried</h2>
<p>Momentum was positive out of sample in {int((m12['out_active'] > 0).sum())} of {len(m12)} settings with 12 industries
and {int((m49['out_active'] > 0).sum())} of {len(m49)} with 49, so the result doesn't rest on one lucky setting.</p>
<details><summary>12 industries</summary><div class="wrap">{grid_table(g12)}</div></details>
<details><summary>49 industries</summary><div class="wrap">{grid_table(g49)}</div></details>
<h2>Halal use</h2>
<p>The sector ETFs themselves don't pass a Shariah screen: the financials fund holds banks and the others include
companies over the debt limits. If a rotation signal were used live, it would mean holding halal-screened stocks
inside the chosen sectors (financials left out), not the ETFs.</p>
<h2>Limits</h2>
<ul>
<li>The industry portfolios can't be bought directly; the ETFs can, but only since 1999 and with different sector
definitions.</li>
<li>Momentum has had sharp losing spells (the worst 12 months trailed all industries by 33%, in 1933).</li>
<li>Costs are a flat 0.10%; taxes are ignored.</li>
</ul>
</main></body></html>"""
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "sectors.html"
    path.write_text(page, encoding="utf-8")
    return str(path)
