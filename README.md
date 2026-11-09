# review-pulse

Do free "alternative data" signals predict a company's results and stock returns? Three signals are tested:

- **Review tone:** how positive the words in a brand's Amazon reviews are
- **Wikipedia interest:** pageviews of the company's and brands' articles
- **Filing wording:** how often negative and uncertainty words appear in its 10-K and 10-Q filings

A University of Michigan study found that the tone of online product reviews predicts quarterly earnings
surprises and abnormal stock returns, and that negative tone matters more. This project tests that idea on
past data, for consumer-product companies that sell heavily on Amazon.

Research only. Not investment advice.

## How it works

1. **Reviews:** the [Amazon Reviews 2023](https://amazon-reviews-2023.github.io/) dataset (McAuley Lab, UCSD).
   We keep reviews of products whose brand store belongs to a configured company. Coverage ends around Sep 2023.
2. **Tone:** a local model (`nlptown/bert-base-multilingual-uncased-sentiment`) reads each review's text and
   scores it from −2 to +2. Up to 1,000 random reviews per fiscal quarter are scored. The star rating the
   reviewer gave is kept separately as a baseline.
3. **Results:** quarterly revenue and net income from SEC EDGAR. Q4 is derived as full year minus Q1–Q3.
   Free analyst estimates don't exist, so "surprise" is approximated by the change in year-over-year
   revenue growth.
4. **Returns:** prices from Yahoo Finance. Abnormal return = stock return minus SPY's return.
5. **Wikipedia:** monthly human pageviews from the Wikimedia API (from July 2015), summed per quarter and
   compared with the same quarter a year earlier.
6. **Filing wording:** each 10-K and 10-Q is downloaded from EDGAR and scored for negative words (decline,
   impairment, headwinds, ...) and uncertainty words per 1,000 words. A filing counts in the quarter it was
   filed and is compared with the same filing type a year earlier.
7. **Tests:** for each quarter, does each signal predict:
   - that quarter's results (announced about a month after the quarter ends)
   - next quarter's results
   - next quarter's abnormal return?

   We report rank correlation "aligned" to each signal's predicted direction (positive = the idea works),
   with each company's own average removed, separate slopes for tone drops and
   rises, and a permutation test: shuffle quarters 2,000 times to see how often luck gives a link this strong.
8. **Robustness:** every pooled result below p=0.05 is re-run on each half of the companies, before and from
   2020, and with each company left out. The report shows whether it holds in every split.

Results so far are in [FINDINGS.md](FINDINGS.md).

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

Steps can also be run one at a time: `fetch`, `score`, `analyze`, `report`. The report is written to
`reports/report.html`.

The dataset files are large (Electronics alone is about 7.8 GB) and are cached in `data/raw/`. Pass
`--delete-raw` to `fetch` to remove them after filtering. `fetch` also lists similar brand-store names
that weren't matched, so you can add missing brands to the config.

## Config

`config/companies.yaml` sets the test window and each company's ticker, fiscal-year-end month, Amazon store
names and dataset categories.

## Limits

- Only reviews up to about Sep 2023. Recent quarters need another source. Wikipedia and filings run to today.
- Many tests are run (3 signals x 3 outcomes x every company), so a few will look significant by chance.
- Revenue-growth change is a rough stand-in for an earnings surprise against analyst estimates.
- Quarter boundaries use calendar months, so 52/53-week fiscal years are off by a few days.
- One company's Amazon reviews cover only part of its sales.

## Tests

```bash
uv run pytest
```
