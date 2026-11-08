"""Paths and company config."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "config" / "companies.yaml"
DATA = ROOT / "data"
RAW = DATA / "raw"          # downloaded dataset files
REVIEWS = DATA / "reviews"  # filtered reviews per company
TONE = DATA / "tone"        # scored reviews per company
FIN = DATA / "financials"
PRICES = DATA / "prices"
REPORTS = ROOT / "reports"


@dataclass
class Company:
    ticker: str
    name: str
    fy_end_month: int
    stores: list[str]
    categories: list[str]
    store_keys: set[str] = field(init=False)

    def __post_init__(self):
        self.store_keys = {normalize_store(s) for s in self.stores}


@dataclass
class Config:
    start: str
    end: str
    companies: dict[str, Company]


def normalize_store(name: str) -> str:
    return " ".join(name.lower().split())


def load_config(path: Path = CONFIG_FILE) -> Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    companies = {
        t: Company(ticker=t, name=c["name"], fy_end_month=int(c["fy_end_month"]),
                   stores=list(c["stores"]), categories=list(c["categories"]))
        for t, c in raw["companies"].items()
    }
    return Config(start=raw["window"]["start"], end=raw["window"]["end"], companies=companies)


def select(cfg: Config, tickers: list[str] | None) -> list[Company]:
    if not tickers:
        return list(cfg.companies.values())
    missing = [t for t in tickers if t.upper() not in cfg.companies]
    if missing:
        raise SystemExit(f"Unknown ticker(s) {missing}. Known: {sorted(cfg.companies)}")
    return [cfg.companies[t.upper()] for t in tickers]
