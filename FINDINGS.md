# Findings

Full charts and tables: `reports/report.html` (open it in a browser).

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
