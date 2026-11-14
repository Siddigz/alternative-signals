"""review-pulse command line."""

import argparse

import pandas as pd

from . import (analysis, congress, copytrade, earnings, filings, financials, insiders, prices, report, reviews,
               short_interest, tone, trends, watchlist, wiki)
from .config import DATA, load_config, select


SOURCES = {  # name: fetch(company, cfg)
    "financials": lambda c, cfg: financials.fetch(c),
    "prices": lambda c, cfg: prices.fetch(c, cfg.start, cfg.end),
    "wiki": lambda c, cfg: wiki.fetch(c),
    "trends": lambda c, cfg: trends.fetch(c),
    "filings": lambda c, cfg: filings.fetch(c, cfg.start),
    "earnings": lambda c, cfg: earnings.fetch(c),
    "insiders": lambda c, cfg: insiders.fetch(c, cfg.start),
    "shorts": lambda c, cfg: short_interest.fetch(c),
}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="review-pulse", description=__doc__)
    p.add_argument("step", choices=["fetch", "score", "analyze", "report", "watchlist", "all",
                                    "congress-fetch", "congress", "congress-alerts", "sectors"])
    p.add_argument("--company", "-c", nargs="*", help="Tickers to run (default: all in config)")
    p.add_argument("--per-quarter", type=int, default=1000, help="Reviews scored per quarter (default 1000)")
    p.add_argument("--min-reviews", type=int, default=30, help="Skip quarters with fewer scored reviews")
    p.add_argument("--skip-reviews", action="store_true",
                   help="fetch: skip Amazon reviews (financials, prices, Wikipedia, filings only)")
    p.add_argument("--delete-raw", action="store_true", help="fetch: delete downloaded dataset files after use")
    p.add_argument("--sources", nargs="*", choices=list(SOURCES), default=list(SOURCES),
                   help="fetch: which non-review sources to fetch (default: all)")
    a = p.parse_args(argv)

    if a.step == "congress-fetch":
        trades = congress.fetch()
        congress.fetch_prices(sorted(copytrade.buys(trades)["ticker"].unique()))
        return
    if a.step == "sectors":
        from . import rotation_report
        r = rotation_report.run()
        print(rotation_report.verdict(r))
        print(rotation_report.cycle_verdict(r["cycle"]))
        print("Report:", rotation_report.write(r))
        return
    if a.step == "congress-alerts":
        from . import alerts
        res = alerts.check()
        print(alerts.summary(res))
        print("Page:", alerts.write(res))
        return
    if a.step == "congress":
        from . import congress_report
        results = copytrade.run()
        results.to_parquet(congress.DIR / "results.parquet", index=False)
        with pd.option_context("display.width", 200, "display.max_columns", 20):
            print(results[["setup", "group", "trades", "members", "alpha_spy", "t_spy",
                           "alpha_qqq", "t_qqq", "beta_qqq"]].round(3).to_string(index=False))
        print("Report:", congress_report.write(results))
        return

    cfg = load_config()
    companies = select(cfg, a.company)
    steps = ["fetch", "score", "analyze", "report", "watchlist"] if a.step == "all" else [a.step]

    if "fetch" in steps:
        if not a.skip_reviews:
            reviews.fetch(companies, cfg.start, cfg.end, keep_raw=not a.delete_raw)
        for c in companies:
            for name in a.sources:
                try:
                    SOURCES[name](c, cfg)
                except (SystemExit, Exception) as e:  # keep going with the other companies
                    print(f"{c.ticker}: {name} FAILED - {e}")

    if "score" in steps:
        scorer = tone.Scorer()
        for c in companies:
            tone.score_company(c, a.per_quarter, scorer)

    panel_path, results_path = DATA / "panel.parquet", DATA / "results.parquet"
    if "analyze" in steps:
        panel = pd.concat([analysis.company_panel(c, cfg.start, a.min_reviews) for c in companies], ignore_index=True)
        panel = analysis.add_sales_surprise(panel)
        results = analysis.run(panel)
        panel.to_parquet(panel_path, index=False)
        results.to_parquet(results_path, index=False)
        print(analysis.verdict(results))

    if "report" in steps:
        panel, results = pd.read_parquet(panel_path), pd.read_parquet(results_path)
        names = {c.ticker: c.name for c in cfg.companies.values()}
        print("Report:", report.write(panel, results, names))

    if "watchlist" in steps:
        panel, results = pd.read_parquet(panel_path), pd.read_parquet(results_path)
        print("Watchlist:", watchlist.write(companies, panel, results))


if __name__ == "__main__":
    main()
