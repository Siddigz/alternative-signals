import numpy as np
import pandas as pd

from review_pulse import analysis
from review_pulse.config import Company
from review_pulse.financials import from_facts
from review_pulse.prices import period_return
from review_pulse.tone import sample_per_quarter, stars_to_tone

ACME = Company(ticker="ACME", name="Acme", fy_end_month=12, stores=["Acme"], categories=["X"])


def test_stars_to_tone():
    probs = np.array([[1, 0, 0, 0, 0], [0, 0, 1, 0, 0], [0, 0, 0, 0, 1], [0.5, 0, 0, 0, 0.5]], float)
    assert stars_to_tone(probs).tolist() == [-2, 0, 2, 0]


def test_sample_per_quarter_caps_each_quarter():
    df = pd.DataFrame({"quarter": ["A"] * 50 + ["B"] * 5, "timestamp": range(55)})
    s = sample_per_quarter(df, 10)
    assert s["quarter"].value_counts().to_dict() == {"A": 10, "B": 5}


def _fact(start, end, val, filed, form="10-Q"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


def test_edgar_quarters_and_derived_q4():
    rev = []
    for y, base in ((2021, 100), (2022, 120)):
        rev += [_fact(f"{y}-01-01", f"{y}-03-31", base, f"{y}-05-01"),
                _fact(f"{y}-04-01", f"{y}-06-30", base, f"{y}-08-01"),
                _fact(f"{y}-07-01", f"{y}-09-30", base, f"{y}-11-01"),
                _fact(f"{y}-01-01", f"{y}-12-31", base * 4 + 50, f"{y + 1}-02-15", "10-K")]
    # A later restatement of Q1 2021 should be ignored (first reported wins).
    rev.append(_fact("2021-01-01", "2021-03-31", 999, "2022-05-01"))
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": rev}}}}}
    df = from_facts(facts, ACME)
    assert df["quarter"].tolist() == [f"FY{y}Q{q}" for y in (2021, 2022) for q in (1, 2, 3, 4)]
    assert df.loc[df["quarter"] == "FY2021Q1", "revenue"].item() == 100
    assert df.loc[df["quarter"] == "FY2021Q4", "revenue"].item() == 150  # 450 - 300
    assert abs(df.loc[df["quarter"] == "FY2022Q1", "rev_yoy"].item() - 0.2) < 1e-9
    # Q4 2022 = 530 - 360 = 170, vs 150 -> 13.3% growth; Q3 growth was 20%.
    assert abs(df.loc[df["quarter"] == "FY2022Q4", "growth_change"].item() - (170 / 150 - 1 - 0.2)) < 1e-9


def test_period_return():
    close = pd.Series([100.0, 110.0, 121.0],
                      index=pd.to_datetime(["2022-12-30", "2023-02-15", "2023-03-31"]))
    assert abs(period_return(close, "2023-01-01", "2023-03-31") - 0.21) < 1e-9
    assert period_return(close, "2022-01-01", "2022-03-31") is None


def test_analysis_finds_planted_signal():
    rng = np.random.default_rng(1)
    rows = []
    for t in ("A", "B", "C"):
        d_tone = rng.normal(0, 0.1, 30)
        for i, x in enumerate(d_tone):
            rows.append({"ticker": t, "quarter": f"Q{i}", "d_tone": x, "d_stars": rng.normal(),
                         "growth_change": rng.normal(), "growth_change_next": rng.normal(),
                         "abn_ret_next": 0.5 * x + rng.normal(0, 0.01)})
    res = analysis.run(pd.DataFrame(rows))
    hit = res[(res["scope"] == "All companies") & (res["signal"] == "tone")
              & (res["outcome"] == "next-quarter return")].iloc[0]
    assert hit["rho"] > 0.8 and hit["perm_p"] < 0.01
    noise = res[(res["scope"] == "All companies") & (res["signal"] == "stars")
                & (res["outcome"] == "next-quarter return")].iloc[0]
    assert abs(noise["rho"]) < 0.3


def test_drop_partial_quarters_trims_tail_only():
    q = pd.DataFrame({"qidx": range(8), "reviews": [100, 20, 110, 105, 98, 102, 40, 9]})
    out = analysis.drop_partial_quarters(q)
    assert out["qidx"].tolist() == [0, 1, 2, 3, 4, 5]
