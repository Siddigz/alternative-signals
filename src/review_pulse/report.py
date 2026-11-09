"""HTML report: verdict, results table, and per-company charts."""

import html
from datetime import date

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .analysis import SIGNALS, verdict
from .config import REPORTS

BLUE, AQUA, GRAY = "#2a78d6", "#1baf7a", "#8a8984"
LAYOUT = dict(template="plotly_white", font=dict(family="system-ui, sans-serif", size=12, color="#0b0b0b"),
              margin=dict(l=60, r=20, t=50, b=40), hovermode="x unified", showlegend=False)

PANELS = [  # column, title, color, y format, hover label
    ("tone", "Average review tone (−2 to +2)", BLUE, ".2f", "Tone"),
    ("wiki_views", "Wikipedia views per quarter", BLUE, "~s", "Views"),
    ("neg_rate", "Negative words per 1,000 in filings", BLUE, ".1f", "Negative words"),
    ("rev_yoy", "Revenue growth vs. same quarter last year", AQUA, ".0%", "Revenue growth"),
    ("abn_ret", "Stock return minus S&P 500 (SPY)", AQUA, ".0%", "Abnormal return"),
]


def company_figure(df: pd.DataFrame, name: str) -> go.Figure:
    panels = [p for p in PANELS if p[0] in df and df[p[0]].notna().any()]
    fig = make_subplots(rows=len(panels), cols=1, shared_xaxes=True, vertical_spacing=0.05,
                        subplot_titles=[p[1] for p in panels])
    x = df["quarter"]
    for row, (col, _, color, fmt, label) in enumerate(panels, start=1):
        hover = f"{label} %{{y:{fmt}}}<extra></extra>"
        if col == "abn_ret":
            trace = go.Bar(x=x, y=df[col], marker=dict(color=color), hovertemplate=hover)
        else:
            trace = go.Scatter(x=x, y=df[col], mode="lines+markers", line=dict(color=color, width=2),
                               marker=dict(size=8), connectgaps=False, hovertemplate=hover)
        fig.add_trace(trace, row=row, col=1)
        fig.update_yaxes(tickformat=fmt, row=row, col=1)
    fig.update_layout(**LAYOUT, height=190 * len(panels) + 80, title=dict(text=name, x=0, font=dict(size=16)))
    fig.update_annotations(font=dict(size=12, color="#52514e"), x=0, xanchor="left")
    return fig


SCATTERS = [("tone", "Review tone change"), ("wikipedia", "Wikipedia views vs. a year earlier (log)"),
            ("filing words", "Filing negative-word rate vs. a year earlier")]


def scatter_figure(panel: pd.DataFrame) -> go.Figure:
    fig = make_subplots(rows=1, cols=3, shared_yaxes=True, horizontal_spacing=0.04,
                        subplot_titles=[t for _, t in SCATTERS])
    for i, (signal, _) in enumerate(SCATTERS, start=1):
        col = SIGNALS[signal][0]
        d = panel.dropna(subset=[col, "abn_ret_next"]) if col in panel else panel.iloc[0:0]
        fig.add_trace(go.Scatter(
            x=d[col] if len(d) else [], y=d["abn_ret_next"] if len(d) else [], mode="markers",
            marker=dict(size=8, color=BLUE, opacity=0.7, line=dict(color="#fcfcfb", width=2)),
            customdata=d[["ticker", "quarter"]] if len(d) else None,
            hovertemplate="%{customdata[0]} %{customdata[1]}<br>Signal %{x:+.2f}"
                          "<br>Next-quarter abnormal return %{y:.1%}<extra></extra>"), row=1, col=i)
        fig.add_hline(y=0, line=dict(color=GRAY, width=1), row=1, col=i)
        fig.add_vline(x=0, line=dict(color=GRAY, width=1), row=1, col=i)
    fig.update_yaxes(tickformat=".0%", title_text="Next-quarter return minus SPY", row=1, col=1)
    fig.update_layout(**{**LAYOUT, "hovermode": "closest"}, height=420,
                      title=dict(text="Each signal vs. the stock's return the next quarter", x=0))
    fig.update_annotations(font=dict(size=12, color="#52514e"))
    return fig


def results_table(results: pd.DataFrame) -> str:
    cols = {"scope": "Scope", "signal": "Signal", "outcome": "Outcome", "n": "Quarters",
            "rho": "Correlation (aligned)", "perm_p": "Luck p-value",
            "slope_neg": "Slope when signal worsens", "slope_pos": "Slope when signal improves"}
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
  main {{ max-width:1100px; margin:0 auto; padding:24px 16px 64px; }}
  h1 {{ font-size:24px; margin:0 0 4px; }} h2 {{ font-size:18px; margin:32px 0 8px; }}
  .muted {{ color:var(--ink2); }}
  .chart {{ background:#fff; border:1px solid var(--line); border-radius:8px; padding:8px; margin:16px 0; }}
  table.results {{ border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums; }}
  table.results th, table.results td {{ text-align:left; padding:4px 8px; border-bottom:1px solid var(--line); }}
  .wrap {{ overflow-x:auto; }}
</style></head><body><main>
<h1>Do review tone, Wikipedia interest and filing wording predict results?</h1>
<p class="muted">Generated {date.today():%Y-%m-%d}. Sources: Amazon Reviews 2023 (McAuley Lab), Wikimedia pageviews,
SEC EDGAR, Yahoo Finance. Research only, not investment advice.</p>
<h2>Verdict (all companies pooled)</h2><ul>{summary}</ul>
<p class="muted">Correlations are "aligned": positive means the signal moved in the direction the idea predicts
(better tone, more interest or calmer filing wording before better outcomes). "Luck p-value" comes from shuffling
quarters within each company 2,000 times; below 0.05 means a link this strong rarely appears by chance. Each
company's own average is removed first. Review data stops in 2023; Wikipedia and filings run to the latest quarter.</p>
<div class="chart">{parts[0]}</div>
<h2>All results</h2><div class="wrap">{results_table(results)}</div>
<h2>By company</h2>
{''.join(f'<div class="chart">{p}</div>' for p in parts[1:])}
</main></body></html>"""
    path = REPORTS / "report.html"
    path.write_text(page, encoding="utf-8")
    return str(path)
