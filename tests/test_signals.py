import numpy as np
import pandas as pd

from alternative_signals import filings, wiki
from alternative_signals.config import Company

ACME = Company(ticker="ACME", name="Acme", fy_end_month=12, stores=["Acme"], categories=["X"], wiki=["Acme"])


def test_word_rates_ignores_markup():
    raw = "<html><style>.loss{}</style><p>Sales declined amid uncertain demand.</p><p>Fine &amp; good.</p></html>"
    r = filings.word_rates(raw)
    assert r["words"] == 7  # sales declined amid uncertain demand fine good
    assert abs(r["neg_rate"] - 1000 / 7) < 1e-9
    assert abs(r["unc_rate"] - 1000 / 7) < 1e-9


def test_filing_change_compares_same_form_a_year_earlier(tmp_path, monkeypatch):
    monkeypatch.setattr(filings, "FILINGS", tmp_path)
    pd.DataFrame({
        "accessionNumber": list("abcde"),
        "filingDate": ["2021-02-20", "2021-05-01", "2022-02-20", "2022-05-01", "2022-05-03"],
        "reportDate": ["2020-12-31", "2021-03-31", "2021-12-31", "2022-03-31", "2022-03-31"],
        "form": ["10-K", "10-Q", "10-K", "10-Q", "10-Q"],
        "words": [1000] * 5, "neg_rate": [10.0, 5.0, 12.0, 4.0, 99.0], "unc_rate": [1.0] * 5,
    }).to_parquet(tmp_path / "ACME.parquet")
    q = filings.quarterly(ACME).set_index("qidx")["filing_chg"]
    assert q.isna().sum() == 2
    assert q.dropna().tolist() == [2.0, -1.0]  # 10-K vs 10-K, 10-Q vs 10-Q; duplicate filing ignored


def test_wiki_yoy(tmp_path, monkeypatch):
    monkeypatch.setattr(wiki, "WIKI", tmp_path)
    months = pd.date_range("2019-01-01", "2021-12-01", freq="MS")
    views = [100] * 12 + [200] * 12 + [200] * 11  # last quarter incomplete
    pd.DataFrame({"month": months[:35], "views": views, "article": "Acme"}).to_parquet(tmp_path / "ACME.parquet")
    q = wiki.quarterly(ACME).set_index("qidx")
    assert len(q) == 11  # incomplete quarter dropped
    y2020 = q.loc[[2020 * 4 + i for i in range(4)], "wiki_yoy"]
    assert np.allclose(y2020, np.log(2))
