"""HTML report: verdict, results table, and per-company charts."""

import html
from datetime import date

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .analysis import OUTCOMES, SIGNALS, robustness, verdict
from .config import REPORTS

BLUE, AQUA, GRAY = "#2a78d6", "#1baf7a", "#8a8984"
ORANGE, NEUTRAL = "#d4572a", "#efeeea"  # diverging poles: blue = predicted direction, orange = opposite
LAYOUT = dict(template="plotly_white", font=dict(family="system-ui, sans-serif", size=12, color="#0b0b0b"),
              margin=dict(l=60, r=20, t=50, b=40), hovermode="x unified", showlegend=False)

PANELS = [  # column, title, color, y format, hover label
    ("tone", "Average review tone (−2 to +2)", BLUE, ".2f", "Tone"),
    ("wiki_views", "Wikipedia views per quarter", BLUE, "~s", "Views"),
    ("trends", "Google search interest per quarter (relative)", BLUE, "~s", "Search interest"),
    ("short_dtc", "Short interest (days to cover)", BLUE, ".1f", "Days to cover"),
    ("rev_yoy", "Revenue growth vs. same quarter last year", AQUA, ".0%", "Revenue growth"),
    ("earn_ret", "Stock move on results day, minus SPY", AQUA, ".0%", "Earnings-day move"),
    ("abn_ret", "Stock return minus S&P 500 (SPY) over the quarter", AQUA, ".0%", "Abnormal return"),
]


def company_figure(df: pd.DataFrame, name: str) -> go.Figure:
    panels = [p for p in PANELS if p[0] in df and df[p[0]].notna().any()]
    fig = make_subplots(rows=len(panels), cols=1, shared_xaxes=True, vertical_spacing=0.05,
                        subplot_titles=[p[1] for p in panels])
    x = df["quarter"]
    for row, (col, _, color, fmt, label) in enumerate(panels, start=1):
        hover = f"{label} %{{y:{fmt}}}<extra></extra>"
        if col in ("abn_ret", "earn_ret"):
            trace = go.Bar(x=x, y=df[col], marker=dict(color=color), hovertemplate=hover)
        else:
            trace = go.Scatter(x=x, y=df[col], mode="lines+markers", line=dict(color=color, width=2),
                               marker=dict(size=8), connectgaps=False, hovertemplate=hover)
        fig.add_trace(trace, row=row, col=1)
        fig.update_yaxes(tickformat=fmt, row=row, col=1)
    fig.update_layout(**LAYOUT, height=190 * len(panels) + 80, title=dict(text=name, x=0, font=dict(size=16)))
    fig.update_annotations(font=dict(size=12, color="#52514e"), x=0, xanchor="left")
    return fig


def grid_figure(results: pd.DataFrame) -> go.Figure:
    """Pooled correlation for every signal (rows) and outcome (columns), labelled with its q-value."""
    pooled = results[results["scope"] == "All companies"].set_index(["signal", "outcome"])
    sig, out = list(SIGNALS), list(OUTCOMES)
    z = [[pooled["rho"].get((s, o), None) for o in out] for s in sig]
    q = pooled["q_value"] if "q_value" in pooled else pooled["perm_p"]
    text = [[("" if z[i][j] is None else f"{z[i][j]:+.2f}<br>q={q.get((s, o)):.2f}") for j, o in enumerate(out)]
            for i, s in enumerate(sig)]
    lim = max(0.15, max(abs(v) for row in z for v in row if v is not None))
    fig = go.Figure(go.Heatmap(
        z=z, x=[o.capitalize() for o in out], y=[s.capitalize() for s in sig], text=text, texttemplate="%{text}",
        zmin=-lim, zmax=lim, colorscale=[[0, ORANGE], [0.5, NEUTRAL], [1, BLUE]], xgap=2, ygap=2,
        colorbar=dict(title="Correlation", tickformat="+.2f"),
        hovertemplate="%{y} vs %{x}<br>Correlation %{z:+.3f}<extra></extra>"))
    fig.update_layout(**{**LAYOUT, "hovermode": "closest"}, height=90 + 56 * len(sig),
                      title=dict(text="Pooled results: blue = worked as predicted, orange = opposite. "
                                      "q below 0.05 survives the many-tests correction.", x=0, font=dict(size=14)))
    fig.update_yaxes(autorange="reversed")
    return fig


def results_table(results: pd.DataFrame) -> str:
    cols = {"scope": "Scope", "signal": "Signal", "outcome": "Outcome", "n": "Quarters",
            "rho": "Correlation (aligned)", "perm_p": "Luck p-value", "q_value": "q (many-tests adjusted)",
            "slope_neg": "Slope when signal worsens", "slope_pos": "Slope when signal improves"}
    t = results[[c for c in cols if c in results]].rename(columns=cols)
    return t.to_html(index=False, float_format=lambda v: f"{v:+.3f}", classes="results", border=0)


def robustness_table(panel: pd.DataFrame, results: pd.DataFrame) -> str:
    """Splits and leave-one-out checks for every pooled result with p < 0.05."""
    pooled = results[(results["scope"] == "All companies") & (results["perm_p"] < 0.05)]
    if pooled.empty:
        return "<p class='muted'>No pooled result below p=0.05, so nothing to check.</p>"
    t = pd.concat([robustness(panel, r.signal, r.outcome) for r in pooled.itertuples()], ignore_index=True)
    t = t.reindex(columns=["test", "check", "n", "rho", "rho_high", "perm_p"]).rename(columns={
        "test": "Pooled result", "check": "Check", "n": "Quarters", "rho": "Correlation (aligned)",
        "rho_high": "Highest", "perm_p": "Luck p-value"})
    return t.to_html(index=False, float_format=lambda v: f"{v:+.3f}", classes="results", border=0, na_rep="")


def write(panel: pd.DataFrame, results: pd.DataFrame, names: dict[str, str]) -> str:
    REPORTS.mkdir(parents=True, exist_ok=True)
    parts = [grid_figure(results).to_html(full_html=False, include_plotlyjs="cdn")]
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
<h1>Do free alternative-data signals predict results and returns?</h1>
<p class="muted">Generated {date.today():%Y-%m-%d}. Sources: Amazon Reviews 2023 (McAuley Lab), Wikimedia pageviews,
SEC EDGAR, Yahoo Finance. Research only, not investment advice.</p>
<h2>Verdict (all companies pooled)</h2><ul>{summary}</ul>
<p class="muted">Correlations are "aligned": positive means the signal moved in the direction the idea predicts
(for example better tone, more insider buying or less short selling before better outcomes). "Luck p-value"
comes from shuffling quarters within each company 2,000 times; "q" adjusts it for the number of tests run, and
below 0.05 counts as a finding. Each company's own average is removed first. Sales surprise = revenue growth vs
a year earlier, minus what last quarter's growth predicted. Earnings-day move = the stock vs SPY around the results
announcement. Review data stops in 2023; the other signals run to the latest quarter.</p>
<div class="chart">{parts[0]}</div>
<h2>Do the pooled results hold up?</h2>
<p class="muted">Each pooled result below p=0.05 is re-run on half the companies, on earlier and later years,
and with each company left out. A real effect should show up, with the same sign, in every split.</p>
<div class="wrap">{robustness_table(panel, results)}</div>
<h2>All results</h2><div class="wrap">{results_table(results)}</div>
<h2>By company</h2>
{''.join(f'<div class="chart">{p}</div>' for p in parts[1:])}
</main></body></html>"""
    path = REPORTS / "report.html"
    path.write_text(page, encoding="utf-8")
    return str(path)
