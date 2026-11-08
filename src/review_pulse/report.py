"""HTML report: verdict, results table, and per-company charts."""

import html
from datetime import date

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .analysis import verdict
from .config import REPORTS

BLUE, AQUA, GRAY = "#2a78d6", "#1baf7a", "#8a8984"
LAYOUT = dict(template="plotly_white", font=dict(family="system-ui, sans-serif", size=12, color="#0b0b0b"),
              margin=dict(l=60, r=20, t=40, b=40), hovermode="x unified", showlegend=False)


def company_figure(df: pd.DataFrame, name: str) -> go.Figure:
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                        subplot_titles=("Average review tone (−2 to +2)",
                                        "Revenue growth vs. same quarter last year",
                                        "Stock return minus S&P 500 (SPY)"))
    x = df["quarter"]
    fig.add_trace(go.Scatter(x=x, y=df["tone"], mode="lines+markers", line=dict(color=BLUE, width=2),
                             marker=dict(size=8), name="Tone",
                             customdata=df[["reviews", "scored", "stars"]],
                             hovertemplate="Tone %{y:.2f}<br>%{customdata[0]:,} reviews "
                                           "(%{customdata[1]:,} scored)<br>Stars %{customdata[2]:.2f}<extra></extra>"),
                  row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=df["rev_yoy"], mode="lines+markers", line=dict(color=AQUA, width=2),
                             marker=dict(size=8), name="Revenue growth",
                             hovertemplate="Revenue growth %{y:.1%}<extra></extra>"), row=2, col=1)
    fig.add_trace(go.Bar(x=x, y=df["abn_ret"], marker=dict(color=BLUE), name="Abnormal return",
                         hovertemplate="Abnormal return %{y:.1%}<extra></extra>"), row=3, col=1)
    fig.update_yaxes(tickformat=".0%", row=2, col=1)
    fig.update_yaxes(tickformat=".0%", row=3, col=1)
    fig.update_layout(**LAYOUT, height=640, title=dict(text=name, x=0, font=dict(size=16)))
    fig.update_annotations(font=dict(size=12, color="#52514e"), x=0, xanchor="left")
    return fig


def scatter_figure(panel: pd.DataFrame) -> go.Figure:
    d = panel.dropna(subset=["d_tone", "abn_ret_next"])
    fig = go.Figure(go.Scatter(
        x=d["d_tone"], y=d["abn_ret_next"], mode="markers",
        marker=dict(size=9, color=BLUE, opacity=0.75, line=dict(color="#fcfcfb", width=2)),
        customdata=d[["ticker", "quarter"]],
        hovertemplate="%{customdata[0]} %{customdata[1]}<br>Tone change %{x:+.2f}"
                      "<br>Next-quarter abnormal return %{y:.1%}<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=GRAY, width=1))
    fig.add_vline(x=0, line=dict(color=GRAY, width=1))
    fig.update_layout(**{**LAYOUT, "hovermode": "closest"}, height=460,
                      title=dict(text="Tone change this quarter vs. stock return next quarter", x=0),
                      xaxis_title="Change in average tone vs. previous quarter",
                      yaxis=dict(title="Next-quarter return minus SPY", tickformat=".0%"))
    return fig


def results_table(results: pd.DataFrame) -> str:
    cols = {"scope": "Scope", "signal": "Signal", "outcome": "Outcome", "n": "Quarters",
            "rho": "Rank corr.", "perm_p": "Luck p-value", "slope_neg": "Slope (tone drops)",
            "slope_pos": "Slope (tone rises)"}
    t = results[list(cols)].rename(columns=cols)
    return t.to_html(index=False, float_format=lambda v: f"{v:+.3f}", classes="results", border=0)


def write(panel: pd.DataFrame, results: pd.DataFrame, names: dict[str, str]) -> str:
    REPORTS.mkdir(parents=True, exist_ok=True)
    parts = [scatter_figure(panel).to_html(full_html=False, include_plotlyjs="cdn")]
    for ticker, df in panel.groupby("ticker"):
        parts.append(company_figure(df, f"{names.get(ticker, ticker)} ({ticker})")
                     .to_html(full_html=False, include_plotlyjs=False))
    summary = "".join(f"<li>{html.escape(line)}</li>" for line in verdict(results).splitlines())
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>review-pulse report</title>
<style>
  :root {{ --bg:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --line:#e4e3df; }}
  body {{ background:var(--bg); color:var(--ink); font:15px/1.5 system-ui,sans-serif; margin:0; }}
  main {{ max-width:1000px; margin:0 auto; padding:24px 16px 64px; }}
  h1 {{ font-size:24px; margin:0 0 4px; }} h2 {{ font-size:18px; margin:32px 0 8px; }}
  .muted {{ color:var(--ink2); }}
  .chart {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:8px; margin:16px 0; }}
  table.results {{ border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums; }}
  table.results th, table.results td {{ text-align:left; padding:4px 8px; border-bottom:1px solid var(--line); }}
  .wrap {{ overflow-x:auto; }}
</style></head><body><main>
<h1>Does review tone predict results?</h1>
<p class="muted">Generated {date.today():%Y-%m-%d}. Amazon Reviews 2023 (McAuley Lab), SEC EDGAR, Yahoo Finance.
Research only, not investment advice.</p>
<h2>Verdict</h2><ul>{summary}</ul>
<p class="muted">Rank correlation runs from −1 to +1; a positive value means tone drops line up with weaker
outcomes. "Luck p-value" is from shuffling quarters within each company 2,000 times: below 0.05 means a link this
strong rarely appears by chance. Each company's own average is removed first.</p>
<div class="chart">{parts[0]}</div>
<h2>All results</h2><div class="wrap">{results_table(results)}</div>
<h2>By company</h2>
{''.join(f'<div class="chart">{p}</div>' for p in parts[1:])}
</main></body></html>"""
    path = REPORTS / "report.html"
    path.write_text(page, encoding="utf-8")
    return str(path)
