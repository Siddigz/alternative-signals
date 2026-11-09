# Findings — first backtest (2026-11-08)

**Short answer: none of the three signals predicted sales or stock returns across these nine companies.**
The video's claim, that a drop in Amazon review tone is followed by a miss, did not hold up here.

Full charts and tables: `reports/report.html` (open it in a browser).

## What was tested

- **Companies (9):** Logitech, YETI, Helen of Troy, Newell Brands, iRobot, GoPro, Sonos, Corsair, Traeger.
- **Period:** 2015 to Sep 2023 for reviews; Wikipedia and filings run to late 2026.
- **Reviews:** about 2.7 million collected, with about 260,000 scored by the tone model (up to 1,000 per company per quarter).
- **Results:** quarterly revenue from SEC EDGAR. Stock returns are measured against the S&P 500.
- **iRobot:** delisted in 2025 and has no free price history, so it is tested on sales only.

## Pooled results (all companies)

"Correlation" is aligned with the idea, so positive means the signal worked as predicted. "p" is the chance
of a link at least this strong appearing by luck.

| Signal | Same-quarter sales | Next-quarter sales | Next-quarter return |
|---|---|---|---|
| Review tone change | −0.04 (p=0.56) | −0.01 (p=0.85) | +0.06 (p=0.41) |
| Star rating change | −0.02 (p=0.80) | −0.03 (p=0.65) | +0.09 (p=0.23) |
| Wikipedia views vs last year | +0.04 (p=0.53) | −0.04 (p=0.49) | −0.01 (p=0.89) |
| Filing negative wording vs last year | −0.15 (p=0.01) | −0.06 (p=0.27) | −0.04 (p=0.56) |

Each cell uses 185–317 company-quarters.

- **Review tone:** no link with anything.
- **Wikipedia:** Logitech's earlier "moderate link" (+0.36) disappeared once all nine companies were included.
  It looks like luck.
- **Filing wording:** the one pooled result below p=0.05 goes the *wrong* way. Gloomier filings came before
  *better* sales growth. The likely reason is that the sales measure snaps back: after a bad stretch, filings
  sound negative and growth rebounds. It is not a usable signal.

## Per-company results

8 of 98 per-company tests came in below p=0.05. About 5 would by chance alone, and 3 of the 8 point the
opposite way from the idea. They are best read as noise.

## Checks that the pipeline works

- Tone scores agree with the star ratings reviewers gave (rank correlation 0.79 over 261,626 reviews), so the
  model reads tone correctly.
- EDGAR revenue matches published figures (e.g. Logitech FY2026 Q4: $1.09B, +7%).
- 15 unit tests pass, including one with a planted signal that the analysis detects.

## Why this may differ from the study

- The study measured surprises against **analyst estimates**. Those aren't free, so we used the change in
  revenue growth as a stand-in, which is noisier.
- The study covered many more firms. Nine companies over about 30 quarters can only detect fairly strong effects.
- Amazon reviews are only part of each company's sales.

## Possible next steps

1. Widen to 30+ companies to detect smaller effects.
2. Use an earnings-surprise measure, if a free source of past analyst estimates can be found.
3. Try other free signals (Google Trends, job postings) through the same tests.
