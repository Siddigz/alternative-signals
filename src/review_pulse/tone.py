"""Score review tone from -2 (very negative) to +2 (very positive) with a local model.

The model (nlptown/bert-base-multilingual-uncased-sentiment) predicts 1-5 stars from text.
Tone = expected stars - 3, so it is continuous in [-2, +2]. It reads only the words, not the
star rating the reviewer gave, which is kept separately as a baseline.
"""

import numpy as np
import pandas as pd
from tqdm import tqdm

from . import reviews
from .config import TONE, Company
from .quarters import add_quarter_columns

MODEL = "nlptown/bert-base-multilingual-uncased-sentiment"
KEY = ["user_id", "parent_asin", "timestamp"]


def stars_to_tone(probs: np.ndarray) -> np.ndarray:
    """probs: (n, 5) probabilities for 1..5 stars -> tone in [-2, 2]."""
    return probs @ np.array([-2.0, -1.0, 0.0, 1.0, 2.0])


def sample_per_quarter(df: pd.DataFrame, per_quarter: int, seed: int = 0) -> pd.DataFrame:
    """At most `per_quarter` reviews per fiscal quarter, sampled at random (stable by seed)."""
    shuffled = df.sample(frac=1.0, random_state=seed)
    return shuffled.groupby("quarter").head(per_quarter).sort_values("timestamp")


class Scorer:
    def __init__(self, batch_size: int = 64, max_length: int = 256):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tok = AutoTokenizer.from_pretrained(MODEL)
        self.model = AutoModelForSequenceClassification.from_pretrained(MODEL).to(self.device).eval()
        if self.device == "cuda":
            self.model.half()
        self.batch_size = batch_size
        self.max_length = max_length
        print(f"Tone model on {self.device}")

    def score(self, texts: list[str]) -> np.ndarray:
        out = []
        for i in tqdm(range(0, len(texts), self.batch_size), desc="scoring", unit=" batch"):
            batch = self.tok(texts[i:i + self.batch_size], truncation=True, padding=True,
                             max_length=self.max_length, return_tensors="pt").to(self.device)
            with self.torch.no_grad():
                logits = self.model(**batch).logits.float()
            out.append(self.torch.softmax(logits, dim=-1).cpu().numpy())
        return stars_to_tone(np.concatenate(out)) if out else np.array([])


def review_text(df: pd.DataFrame) -> list[str]:
    return (df["title"].fillna("") + ". " + df["text"].fillna("")).str.slice(0, 2000).tolist()


def score_company(company: Company, per_quarter: int, scorer: Scorer | None = None) -> pd.DataFrame:
    """Score a sample of each quarter's reviews, reusing cached scores. Writes data/tone/{ticker}.parquet."""
    df = add_quarter_columns(reviews.load(company.ticker), "date", company.fy_end_month)
    sample = sample_per_quarter(df, per_quarter)

    TONE.mkdir(parents=True, exist_ok=True)
    path = TONE / f"{company.ticker}.parquet"
    cached = pd.read_parquet(path)[KEY + ["tone"]] if path.exists() else pd.DataFrame(columns=KEY + ["tone"])
    sample = sample.merge(cached, on=KEY, how="left")
    todo = sample["tone"].isna()
    print(f"{company.ticker}: {len(sample):,} sampled reviews, {todo.sum():,} to score")
    if todo.any():
        scorer = scorer or Scorer()
        sample.loc[todo, "tone"] = scorer.score(review_text(sample[todo]))

    keep = sample.drop(columns=["text", "title"])
    all_scored = pd.concat([pd.read_parquet(path), keep]) if path.exists() else keep
    all_scored = all_scored.drop_duplicates(KEY, keep="last")
    all_scored.to_parquet(path, index=False)
    return keep


def quarterly(company: Company) -> pd.DataFrame:
    """Per fiscal quarter: mean tone (scored sample), mean stars and review count (all reviews)."""
    path = TONE / f"{company.ticker}.parquet"
    if not path.exists():
        raise SystemExit(f"No tone scores for {company.ticker}. Run: review-pulse score --company {company.ticker}")
    scored = pd.read_parquet(path)
    allr = add_quarter_columns(reviews.load(company.ticker), "date", company.fy_end_month)
    t = scored.groupby(["qidx", "quarter"]).agg(
        tone=("tone", "mean"),
        neg_share=("tone", lambda s: (s < -0.5).mean()),
        scored=("tone", "size"))
    s = allr.groupby(["qidx", "quarter"]).agg(stars=("rating", "mean"), reviews=("rating", "size"))
    return t.join(s, how="outer").reset_index().sort_values("qidx")
