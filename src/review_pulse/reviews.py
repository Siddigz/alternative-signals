"""Download Amazon Reviews 2023 (McAuley Lab, UCSD) and keep reviews for configured brands.

Each category has a product file (meta_*.jsonl.gz, with the brand "store") and a review file.
One pass over the product file finds the companies' product IDs (parent_asin); one pass over the
review file keeps reviews of those products. Files are cached under data/raw/.
"""

import gzip
from collections import Counter, defaultdict
from pathlib import Path

import orjson
import pandas as pd
import requests
from tqdm import tqdm

from .config import RAW, REVIEWS, Company, normalize_store

BASE = "https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/raw"
PARENT_KEY = b'"parent_asin": "'


def category_urls(category: str) -> tuple[str, str]:
    return (f"{BASE}/meta_categories/meta_{category}.jsonl.gz",
            f"{BASE}/review_categories/{category}.jsonl.gz")


def download(url: str, dest: Path) -> Path:
    """Download with resume. Skips files that are already complete."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = int(requests.head(url, timeout=30).headers.get("Content-Length", 0))
    have = dest.stat().st_size if dest.exists() else 0
    if total and have == total:
        return dest
    headers = {"Range": f"bytes={have}-"} if have else {}
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        mode = "ab" if have and r.status_code == 206 else "wb"
        if mode == "wb":
            have = 0
        with open(dest, mode) as f, tqdm(total=total, initial=have, unit="B", unit_scale=True,
                                          desc=dest.name) as bar:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                bar.update(len(chunk))
    return dest


def find_products(meta_file: Path, companies: list[Company]) -> tuple[dict, dict]:
    """Map parent_asin -> (ticker, store) for products whose store belongs to a company.

    Also returns, per company, a Counter of *unmatched* store names that contain one of the
    company's store names, to help spot brand pages missing from the config.
    """
    by_key = {key: c.ticker for c in companies for key in c.store_keys}
    needles = [k.encode() for k in by_key]
    products: dict[str, tuple[str, str]] = {}
    near_misses: dict[str, Counter] = defaultdict(Counter)
    with gzip.open(meta_file, "rb") as f:
        for line in tqdm(f, desc=f"products {meta_file.name}", unit=" items", mininterval=2):
            low = line.lower()
            if not any(n in low for n in needles):
                continue
            item = orjson.loads(line)
            store = item.get("store") or ""
            key = normalize_store(store)
            if key in by_key:
                products[item["parent_asin"]] = (by_key[key], store)
            else:
                for k, t in by_key.items():
                    if len(k) > 3 and k in key:
                        near_misses[t][store] += 1
    return products, near_misses


def filter_reviews(review_file: Path, products: dict, start_ms: int, end_ms: int,
                   category: str) -> list[dict]:
    rows = []
    with gzip.open(review_file, "rb") as f:
        for line in tqdm(f, desc=f"reviews {review_file.name}", unit=" reviews", mininterval=2):
            i = line.find(PARENT_KEY)
            if i < 0:
                continue
            j = i + len(PARENT_KEY)
            pid = line[j:line.find(b'"', j)].decode()
            hit = products.get(pid)
            if hit is None:
                continue
            r = orjson.loads(line)
            ts = int(r["timestamp"])
            if not (start_ms <= ts <= end_ms):
                continue
            rows.append({
                "ticker": hit[0], "store": hit[1], "category": category,
                "parent_asin": pid, "asin": r.get("asin"), "user_id": r.get("user_id"),
                "timestamp": ts, "rating": float(r["rating"]),
                "title": r.get("title") or "", "text": r.get("text") or "",
                "verified_purchase": bool(r.get("verified_purchase")),
                "helpful_vote": int(r.get("helpful_vote") or 0),
            })
    return rows


def fetch(companies: list[Company], start: str, end: str, keep_raw: bool = True) -> None:
    """Build data/reviews/{ticker}.parquet for each company."""
    start_ms = int(pd.Timestamp(start).timestamp() * 1000)
    end_ms = int((pd.Timestamp(end) + pd.Timedelta(days=1)).timestamp() * 1000) - 1
    by_category: dict[str, list[Company]] = defaultdict(list)
    for c in companies:
        for cat in c.categories:
            by_category[cat].append(c)

    rows: list[dict] = []
    misses: dict[str, Counter] = defaultdict(Counter)
    for cat, comps in by_category.items():
        meta_url, review_url = category_urls(cat)
        meta_file = download(meta_url, RAW / Path(meta_url).name)
        products, near = find_products(meta_file, comps)
        for t, cnt in near.items():
            misses[t].update(cnt)
        print(f"{cat}: {len(products):,} matching products")
        if not products:
            continue
        review_file = download(review_url, RAW / Path(review_url).name)
        rows += filter_reviews(review_file, products, start_ms, end_ms, cat)
        if not keep_raw:
            meta_file.unlink(missing_ok=True)
            review_file.unlink(missing_ok=True)

    REVIEWS.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    for c in companies:
        sub = df[df["ticker"] == c.ticker] if len(df) else df
        if len(sub):
            # Same review can appear in two categories; keep one.
            sub = sub.drop_duplicates(["user_id", "parent_asin", "timestamp"])
        sub.to_parquet(REVIEWS / f"{c.ticker}.parquet", index=False)
        stores = sub["store"].value_counts() if len(sub) else pd.Series(dtype=int)
        print(f"\n{c.ticker}: {len(sub):,} reviews")
        for s, n in stores.items():
            print(f"  {s}: {n:,}")
        if misses[c.ticker]:
            print("  Similar store names NOT included (add to config if they belong):")
            for s, n in misses[c.ticker].most_common(8):
                print(f"    {s!r}: {n:,} products")


def load(ticker: str) -> pd.DataFrame:
    path = REVIEWS / f"{ticker}.parquet"
    if not path.exists():
        raise SystemExit(f"No reviews for {ticker}. Run: review-pulse fetch --company {ticker}")
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms").dt.date
    return df
