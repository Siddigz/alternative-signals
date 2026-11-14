# review-pulse

Do free "alternative data" signals predict a company's results and stock returns? Seven signals are tested:

- **Review tone and star rating:** how positive a brand's Amazon reviews are (to 2023)
- **Wikipedia interest:** pageviews of the company's and brands' articles
- **Google search interest:** Google Trends for the main brand names
- **Filing wording:** how often negative and uncertainty words appear in its 10-K and 10-Q filings
- **Insider buying:** open-market buys and sells by directors and officers (SEC Form 4)
- **Short interest:** how heavily traders are betting against the stock (FINRA)

A University of Michigan study found that the tone of online product reviews predicts quarterly earnings
surprises and abnormal stock returns, and that negative tone matters more. This project tests that idea, and
the other signals, on past data for consumer-product companies that sell heavily on Amazon. A watchlist page
shows each company's latest readings and a halal (Shariah) screen for live use.

Research only. Not investment advice.

## How it works

1. **Reviews:** the [Amazon Reviews 2023](https://amazon-reviews-2023.github.io/) dataset (McAuley Lab, UCSD).
   We keep reviews of products whose brand store belongs to a configured company. Coverage ends around Sep 2023.
2. **Tone:** a local model (`nlptown/bert-base-multilingual-uncased-sentiment`) reads each review's text and
   scores it from −2 to +2. Up to 1,000 random reviews per fiscal quarter are scored. The star rating the
   reviewer gave is kept separately as a baseline.
3. **Results:** quarterly revenue from SEC EDGAR. Q4 is derived as full year minus Q1–Q3.
4. **Returns:** prices from Yahoo Finance. Abnormal return = stock return minus SPY's return.
5. **Wikipedia:** monthly human pageviews from the Wikimedia API (from July 2015), summed per quarter and
   compared with the same quarter a year earlier.
6. **Google search:** monthly US Google Trends interest (from 2015) for up to five brand terms, compared with
   the same quarter a year earlier. Uses the unofficial `pytrends` client, which Google rate-limits.
7. **Filing wording:** each 10-K and 10-Q is downloaded from EDGAR and scored for negative words (decline,
   impairment, headwinds, ...) and uncertainty words per 1,000 words. A filing counts in the quarter it was
   filed and is compared with the same filing type a year earlier.
8. **Insider buying:** every Form 4 filed for the company. Per quarter, (insiders buying − insiders selling) /
   (buying + selling), counting open-market trades only.
9. **Short interest:** FINRA's twice-monthly short positions (free, from Dec 2017), as days to cover.
10. **Outcomes:** for each quarter, does each signal predict:
    - **sales surprise:** year-over-year revenue growth minus what last quarter's growth predicted (growth
      persists but partly reverts; the forecast is a pooled regression). Analyst estimates aren't free, so
      this stands in for a beat or miss.
    - **next quarter's sales surprise**
    - **earnings-day move:** the stock's move versus SPY around the results announcement (8-K item 2.02),
      from the close before to the close of the second trading day. The price already holds what investors
      expected, so the move shows how far results differed.
    - **next quarter's abnormal return**
11. **Tests:** rank correlation "aligned" to each signal's predicted direction (positive = the idea works),
    with each company's own average removed, separate slopes for drops and rises, and a permutation test that
    shuffles quarters within each company 2,000 times. A q-value (Benjamini-Hochberg) allows for the number of
    tests run.
12. **Robustness:** every pooled result below p=0.05 is re-run on each half of the companies, before and from
    2020, and with each company left out. The report shows whether it holds in every split.
13. **Watchlist and halal screen:** `reports/watchlist.html` shows each company's latest signal readings
    against its own history, its last earnings-day move, and an AAOIFI-style financial screen: interest-bearing
    debt and cash+securities each under 30% of market value, interest income under 5% of revenue. Whether the
    business itself is permissible is set by hand in the config (`halal_business`, `halal_note`).

Results so far are in [FINDINGS.md](FINDINGS.md).

## Copying Congress

A separate backtest tests the claim that you can profit by copying the stock buys of the best-performing
members of Congress once their trades are disclosed (`reports/congress.html`).

1. **Data:** every House periodic transaction report (STOCK Act) since 2014, from the House Clerk's site.
   Electronic reports are parsed; paper reports are scanned images and are skipped (most reports before 2018,
   about 13% now).
2. **Picking whom to copy:** each year, members are ranked by how their disclosed buys did against SPY over
   the previous two years, counting only trades whose holding period had ended before the year began, so no
   future information is used. The top 30 are copied.
3. **Copying:** buy at the close of the first trading day after the report was filed, hold about six months.
4. **Scoring:** daily returns of the copied portfolio against SPY and QQQ (alpha and beta, Newey-West t-stats),
   next to copying every member and copying the worst-ranked members. Variants change the hold, list size,
   ranking window, years, drop options, or keep only shares in permissible (halal) industries.

```bash
uv run review-pulse congress-fetch   # download and parse reports, then prices (about an hour the first time)
uv run review-pulse congress         # run the backtest and write reports/congress.html
uv run review-pulse congress-alerts  # daily check: new buys by this year's top-ranked members, halal-screened
```

## Sector rotation

Does holding the sectors a signal ranks highest beat holding every sector (`reports/sectors.html`)?

1. **Data:** Ken French's monthly US industry returns (12 and 49 industries, 1926–today) and the SPDR sector
   ETFs (1999–today).
2. **Rule:** each month, rank sectors by momentum, short-term reversal or low volatility (using only data up
   to that month), hold the top 2–4 in equal weight, and pay 0.10% per trade.
3. **Out-of-sample test:** each signal's settings are chosen on 1927–1989, then tested unchanged on
   1990–today and on the ETFs, with Holm-adjusted p-values.
4. **Business cycle:** FRED indicators (yield curve, inflation, industrial production, unemployment), each used
   from the month it was published. Tests a switch to defensive sectors during slowdown warnings, momentum with
   that switch, and a regression forecast refitted monthly on past data; settings chosen on 1955–1989.

```bash
uv run review-pulse sectors
```

## Setup

Needs [uv](https://docs.astral.sh/uv/). The default install is the CUDA build of PyTorch. For a CPU-only
machine, delete the `[tool.uv.sources]` and `[[tool.uv.index]]` tables in `pyproject.toml`.

```bash
uv sync
cp .env.example .env   # then set SEC_USER_AGENT="Your Name you@example.com" (SEC requires a contact)
```

## Run

```bash
uv run review-pulse all --company LOGI      # one company end to end
uv run review-pulse all                     # every company in config/companies.yaml
```

Steps can also be run one at a time: `fetch`, `score`, `analyze`, `report`, `watchlist`. The report is written
to `reports/report.html` and the watchlist to `reports/watchlist.html`. `fetch --skip-reviews --sources ...`
fetches only some sources (financials, prices, wiki, trends, filings, earnings, insiders, shorts).

The dataset files are large (Electronics alone is about 7.8 GB) and are cached in `data/raw/`. Pass
`--delete-raw` to `fetch` to remove them after filtering. `fetch` also lists similar brand-store names
that weren't matched, so you can add missing brands to the config.

## Config

`config/companies.yaml` sets the test window and each company's ticker, fiscal-year-end month, Amazon store
names and dataset categories.

## Limits

- Only reviews up to about Sep 2023. Recent quarters need another source. Wikipedia and filings run to today.
- Many tests are run (7 signals x 4 outcomes x every company), so a few will look significant by chance; q-values allow for this.
- The sales surprise and earnings-day move are stand-ins for a surprise against analyst estimates.
- The halal screen is a research aid, not a ruling. Confirm with a scholar or a screening service.
- Quarter boundaries use calendar months, so 52/53-week fiscal years are off by a few days.
- One company's Amazon reviews cover only part of its sales.

## Tests

```bash
uv run pytest
```
