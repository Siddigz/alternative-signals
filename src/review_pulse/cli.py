"""review-pulse command line."""

import argparse

import pandas as pd

from . import analysis, filings, financials, prices, report, reviews, tone, wiki
from .config import DATA, load_config, select


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="review-pulse", description=__doc__)
    p.add_argument("step", choices=["fetch", "score", "analyze", "report", "all"])
    p.add_argument("--company", "-c", nargs="*", help="Tickers to run (default: all in config)")
    p.add_argument("--per-quarter", type=int, default=1000, help="Reviews scored per quarter (default 1000)")
    p.add_argument("--min-reviews", type=int, default=30, help="Skip quarters with fewer scored reviews")
    p.add_argument("--skip-reviews", action="store_true",
                   help="fetch: skip Amazon reviews (financials, prices, Wikipedia, filings only)")
    p.add_argument("--delete-raw", action="store_true", help="fetch: delete downloaded dataset files after use")
    a = p.parse_args(argv)

    cfg = load_config()
    companies = select(cfg, a.company)
    steps = ["fetch", "score", "analyze", "report"] if a.step == "all" else [a.step]

    if "fetch" in steps:
        if not a.skip_reviews:
            reviews.fetch(companies, cfg.start, cfg.end, keep_raw=not a.delete_raw)
        for c in companies:
            financials.fetch(c)
            prices.fetch(c, cfg.start, cfg.end)
            wiki.fetch(c)
            filings.fetch(c, cfg.start)

    if "score" in steps:
        scorer = tone.Scorer()
        for c in companies:
            tone.score_company(c, a.per_quarter, scorer)

    panel_path, results_path = DATA / "panel.parquet", DATA / "results.parquet"
    if "analyze" in steps:
        panel = pd.concat([analysis.company_panel(c, cfg.start, a.min_reviews) for c in companies], ignore_index=True)
        results = analysis.run(panel)
        panel.to_parquet(panel_path, index=False)
        results.to_parquet(results_path, index=False)
        print(analysis.verdict(results))

    if "report" in steps:
        panel, results = pd.read_parquet(panel_path), pd.read_parquet(results_path)
        names = {c.ticker: c.name for c in cfg.companies.values()}
        print("Report:", report.write(panel, results, names))


if __name__ == "__main__":
    main()
