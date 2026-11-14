# Findings

Full charts and tables: `reports/report.html` (open it in a browser).

## Sector rotation, step 1: price signals (2026-11-14)

**Short answer: industry momentum is real but has faded, and it doesn't show up in the sector ETFs you
can buy.** Holding the 3 industries with the best past year beat holding all 12 by 3.3% a year from 1990
to 2026 (t 3.1). The rule was chosen only on 1927–1989 data, so this is a true out-of-sample result.

- **Since 1999 it's weaker:** +2.6% a year (t 1.6).
- **By decade:** close to nothing in the 2000s and 2010s, then +5% a year in the 2020s.
- **On the SPDR sector ETFs** (1999–2026) the same rule added +0.9% a year (t 0.7), which could easily be luck.

Full page: `reports/sectors.html`.

### What was tested

- **Data:**
  - Ken French's monthly returns for 12 and 49 US industries, 1926–2026.
  - The 11 SPDR sector ETFs, 1999–2026.
- **Rule:** each month, hold the top-ranked sectors in equal weight, with a 0.10% trading cost, against
  holding every sector equally.
- **Signals and settings:**
  - Momentum: look-back of 3, 6, 9 or 12 months, with or without skipping the latest month.
  - Short-term reversal: buy last month's losers.
  - Low volatility: hold the calmest sectors.
  - Each held the top 2, 3 or 4 sectors.
- **Selection:** each signal's best setting on 1927–1989 was tested unchanged on 1990–2026 and on the ETFs.
  Holm-adjusted p-values allow for testing three signals.

### Results (1990–2026, vs all 12 industries)

| Signal (chosen on 1927–1989) | Yearly gain vs all | t | Holm p | ETFs 1999–2026 alpha (t) |
|---|---|---|---|---|
| Momentum, 12 months, top 3 | +3.3% | 3.1 | < 0.01 | +0.9% (0.7) |
| Reversal, top 2 | −6.8% | −5.4 | – | −3.6% (−2.2) |
| Low volatility, 36 months, top 4 | −2.1% | 0.0 | – | +0.3% (0.3) |

- Momentum was positive out of sample in 22 of 24 settings, with both 12 and 49 industries.
- Reversal lost badly. At the industry level last month's winners keep winning, which is momentum again.
- Momentum trades about 5 times the portfolio a year, and it has had sharp losing spells: the worst 12 months
  trailed all industries by 33%, in 1933.

### What it means

The idea has a century of support, but recent decades are much weaker. On the ETFs a real investor would
use, it can't be told apart from luck. It's not worth trading on its own. Steps 2 and 3 test whether the
business cycle or our alt data (insider and Congress buying by sector) add anything.

### Halal

The sector ETFs don't pass a Shariah screen: the financials fund holds banks, and the others include
companies over the debt limits. Live use would mean halal-screened stocks within the chosen sectors, with
financials left out.

## Copying Congress (2026-11-13)

**Short answer: no. Copying the House members with the best past record, from the day their trades were
disclosed, did no better than copying every member, and no group beat SPY or QQQ by more than luck would
explain. The worst-ranked members actually did slightly better than the best-ranked.**

This tests a popular Reddit guide that says the top 30 politicians beat the market even after the filing
delay. Full page: `reports/congress.html`.

### What was tested

- **Data:**
  - Every electronically filed House trade report from 2014 to now: 5,991 reports with 54,887 transactions
    by 303 members.
  - Of those, 18,621 stock and call-option buys can be copied, and 88% of them have price history.
- **Picking whom to copy:**
  - Each year, rank members by how their past buys did against SPY.
  - The main setup uses the previous two years, counting only trades whose six-month hold had already
    ended, so no hindsight.
  - Copy the top 30.
- **Copying:** buy at the close of the first trading day after the report was filed, then hold six months.
- **Checks:** copying everyone, copying the bottom 30, and ten variants:
  - holds of 1 and 3 months
  - top 10 instead of top 30
  - 1- or 3-year records
  - no options
  - 2016–2019 and 2020 onward separately
  - a halal-only version

### Results (alpha a year, t-statistic in brackets; about 2 or more would be unlikely to be luck)

| Setup | Top members vs QQQ | Every member vs QQQ | Bottom members vs QQQ |
|---|---|---|---|
| Main (top 30, 2-year record, hold 6 months) | +1.2% (0.4) | +1.1% (0.3) | +3.1% (0.9) |
| 2016–2019 | −3.6% (−0.7) | −2.6% (−0.5) | −2.3% (−0.5) |
| 2020 on | +0.3% (0.1) | +0.6% (0.1) | +3.2% (0.6) |
| Halal: shares only, permissible industries | +2.0% (0.6) | +1.3% (0.4) | +3.3% (1.0) |

- Against SPY the main top group is +0.1% a year (t 0.1).
- None of the 30 group-and-setup results reaches t = 2.
- The top group beat the all-members group in only 5 of 10 setups, a coin flip.
- Ranking on past results doesn't find people who keep winning.

### What the reporting delay costs

- The median trade is reported 28 days after it happens, and 17% are later than the 45 days the law allows.
- Pelosi's buys (75 with prices) beat SPY by 5.5% per six months measured from the trade date. Measured from
  the disclosure date, that drops to 2.8%: the delay costs about half her edge.
- What's left (+7% a year vs QQQ, t 1.2) isn't distinguishable from luck over 75 trades, many of them call options.

### Gaps

- **Paper filings aren't read.** Ro Khanna (121 reports) and Michael McCaul (153) file only on paper, so the
  members the Reddit guide rates highest are missing entirely. Reading them needs OCR.
- **The Senate isn't included.**
- **Delisted stocks are dropped.** They have no free price history, which flatters every group a little.
- **The halal version screens industries only.** It doesn't apply the debt and cash ratios as they were at the
  time of each trade.

### Daily check

`review-pulse congress-alerts` downloads new House reports, lists buys by this year's top-ranked members from
the last 7 days, runs each stock through the halal screen, and writes `reports/congress_alerts.html`. Given
the backtest, treat it as a news feed, not a trading signal.

## Third backtest: 40 companies, 7 signals, 4 outcomes (2026-11-10)

**Short answer: Google search interest is the first signal that holds up. When searches for a company's
brands rise faster than a year earlier, that quarter's sales tend to beat what past growth predicted, and
the stock tends to do slightly better than the market the next quarter. Review tone still predicts nothing.
High short interest came before weaker returns, but less consistently.**

### What changed

- **Companies (40):** the 34 from the second run plus Procter & Gamble, Colgate-Palmolive, Kimberly-Clark,
  Spectrum Brands, Vista Outdoor and Somnigroup (Tempur Sealy).
- **New signals:** Google search interest (Google Trends), insider buying (SEC Form 4), short interest (FINRA).
- **Better outcomes:**
  - **Sales surprise:** growth minus what last quarter's growth predicted. Growth carries over at about 0.54
    per quarter, so a firm growing 10% is expected to grow about 5.4% above its usual rate the next quarter.
  - **Earnings-day move:** the stock versus SPY from the day before results to the second day after.
  - Next quarter's sales surprise and abnormal return.
- **q-values** allow for running 28 pooled tests and 1,051 per-company tests.

### Pooled results (q < 0.05 only)

| Signal | Outcome | Correlation | q | Holds in every split? |
|---|---|---|---|---|
| Google search | sales surprise | +0.20 | 0.005 | yes: both halves of companies, before and from 2020, leave-one-out 0.18–0.21, 34 of 40 companies |
| Google search | next sales surprise | +0.14 | 0.005 | only from 2020 (before 2020: +0.03) |
| Google search | next-quarter return | +0.10 | 0.005 | yes: halves +0.08/+0.11, before/from 2020 +0.12/+0.09, 27 of 37 companies |
| Short interest | next-quarter return | +0.09 | 0.007 | same sign everywhere, but weak before 2020 (p=0.25) and from 2020 (p=0.08) |
| Stars | next-quarter return | +0.09 | 0.020 | no: zero before 2020 (+0.02), +0.16 from 2020 |
| Filing words | next-quarter return | −0.06 | 0.026 | opposite to the idea; likely the same artifact as before |

Everything else, including tone, Wikipedia and insider buying, showed no link.
Google search barely moves the earnings-day return (+0.05, q=0.17), so investors seem to price most of it in
before results come out. The next-quarter return effect is small: a correlation of 0.10 explains about 1% of
the variation.

Per company, 93 of 1,051 tests had p < 0.05 (about 53 expected by chance) and none survived the q-value.
Single companies have too few quarters to say much on their own.

### Caveats

- Google Trends data is downloaded today. Google samples and rescales it, so the values seen at the time
  may have differed slightly.
- Brand search terms were picked by hand, by name, without looking at results.
- Analyst estimates aren't free, so "sales surprise" is a stand-in for a beat or miss.

### Watchlist and halal screen

`reports/watchlist.html` lists all 40 companies with an AAOIFI ratio screen and each live signal's latest
reading. Google search and short interest are marked as passing the backtest. 20 companies pass the
financial ratios (none is fully cleared until its business is reviewed by hand) and 20 fail, mostly on debt.

### Not done

- **Best Buy reviews:** needs a free API key (`BESTBUY_API_KEY` in `.env`), which isn't set yet.
- **App store reviews:** only recent reviews are available, so they can't be backtested; live use only.

## Second backtest: 34 companies (2026-11-09)

**Short answer: review tone, Wikipedia views and filing wording still predict nothing. One weak lead turned
up: a rise in a brand's average Amazon star rating came before a slightly better stock return the next
quarter. It appears only in 2020–2023, so it is not something to trade on.**

### What was tested

- **Companies (34):** the first nine plus 25 more consumer-brand firms:
  - **Electronics:** Garmin, Turtle Beach, Netgear, Arlo, Koss
  - **Home:** Hamilton Beach, Lifetime Brands, Tupperware, National Presto
  - **Household and beauty:** Clorox, e.l.f., Coty, Edgewell, Energizer, Church & Dwight, Prestige Consumer Healthcare
  - **Outdoor:** Johnson Outdoors, Clarus
  - **Toys:** Hasbro, Mattel, Jakks Pacific, Funko
  - **Garden and pet:** Central Garden & Pet, Scotts Miracle-Gro
  - **Office:** ACCO Brands
- **Reviews:** about 7 million collected, with about 1,000 per company per quarter scored for tone.
- **Coverage:** roughly 900–1,400 company-quarters per test, five times the first run.
- **Data gaps:**
  - Tupperware and iRobot are delisted with no free price history, so they get sales tests only.
  - Lifetime Brands and Central Garden have too little Wikipedia history for that signal.
- **Dropped:** Peloton (14 products in the dataset) and Purple (no matching store).

### Pooled results

Positive correlation = the signal worked in the direction the idea predicts. "p" = chance of a link this
strong from luck alone.

| Signal | Same-quarter sales | Next-quarter sales | Next-quarter return |
|---|---|---|---|
| Review tone change | +0.00 (p=0.97) | −0.04 (p=0.19) | +0.06 (p=0.06) |
| Star rating change | +0.03 (p=0.32) | −0.03 (p=0.32) | **+0.10 (p=0.006)** |
| Wikipedia views vs last year | +0.03 (p=0.24) | +0.00 (p=0.94) | +0.02 (p=0.44) |
| Filing negative wording vs last year | −0.14 (p<0.001) | −0.12 (p=0.001) | −0.05 (p=0.06) |

### The star-rating lead

Quarters where a brand's average star rating rose, compared with its own norm, were followed by better stock
returns against the S&P 500.

- **Size:** the bottom 40% of rating changes averaged about −4% the next quarter; the top 60% averaged about +2.5%.
- **What holds up:**
  - Both halves of the companies show it: +0.10 and +0.09.
  - The first nine companies (+0.09) and the 25 new ones (+0.10) agree, which is close to a fresh replication.
  - Leaving out any single company keeps it between +0.09 and +0.11.
  - 20 of 31 companies point the same way.
- **What doesn't:**
  - **Time:** it is zero before 2020 (+0.02, p=0.63) and comes entirely from fiscal 2020–2023 (+0.18).
    That period includes COVID's shifts in online shopping, and the dataset thins out near its 2023 end.
  - **Many tests:** 12 pooled tests were run. Demanding p<0.004 to allow for that, it just misses.
  - **Tone:** the tone model agrees less: +0.06, p=0.06.
- **Read it as:** a lead worth checking on newer data, not a proven signal. The dataset stops in 2023,
  so testing 2024 onward needs a fresh review source.

### Filing wording: a built-in result, not a forecast

Gloomier filings come before *better* sales growth. This holds in every split and in 32 of 34 companies,
which points to something built into the measure rather than a market effect:

- A filing made in quarter t describes quarter t−1. Its gloomy wording tracks weak growth in t−1 (correlation −0.28).
- The sales measure, change in growth, subtracts t−1's growth. A weak t−1 therefore makes it look like a rebound.

The wording describes the past. It doesn't predict anything.

### Per-company results

34 of 388 per-company tests came in below p=0.05, against about 19 expected by luck. 24 of those 34 point the
wrong way, mostly the built-in filing effect above. The rest are best read as noise.

## First backtest: 9 companies (2026-11-08)

- **Companies:** Logitech, YETI, Helen of Troy, Newell Brands, iRobot, GoPro, Sonos, Corsair, Traeger.
- **Result:** nothing predicted sales or returns.
- **Wikipedia:** Logitech's +0.36 link with Wikipedia views vanished once the other companies were added.
- **Star rating:** this run's +0.09 for star rating vs next return (p=0.23) was too small to detect with 185 quarters.

## Checks that the pipeline works

- Tone scores agree with the star ratings reviewers gave (rank correlation 0.79 over 261,626 reviews).
- EDGAR revenue matches published figures (e.g. Logitech FY2026 Q4: $1.09B, +7%).
- 16 unit tests pass, including planted signals that the analysis and the robustness checks detect.

## Why this may differ from the study

- The study measured surprises against **analyst estimates**. Those aren't free, so we used the change in
  revenue growth as a stand-in. That stand-in also causes the built-in filing-wording result.
- Amazon reviews are only part of each company's sales.

## Possible next steps

1. Test the star-rating lead on 2024+ data from a fresh review source. That is the only out-of-sample check left.
2. Replace the sales measure with one that doesn't subtract last quarter, such as growth vs the same quarter last year.
3. Use an earnings-surprise measure, if a free source of past analyst estimates can be found.
