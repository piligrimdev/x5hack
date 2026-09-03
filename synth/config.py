from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml


@dataclass
class CategoryConfig:
    name: str
    items: list[str]


@dataclass
class CalibrationConfig:
    avg_receipt_total_rub: float
    purchases_per_month_mean: float
    purchases_per_month_stddev: float
    offline_share: float
    source: str


@dataclass
class ChainConfig:
    name: str
    price_multiplier: float
    segment_weights: dict[str, float]


@dataclass
class SegmentConfig:
    name: str
    visit_frequency_multiplier: float
    basket_size_multiplier: float


@dataclass
class CategoryEconomicsConfig:
    category: str
    base_price_rub: float
    price_jitter_pct: float
    margin_pct: float
    popularity_weight: float


@dataclass
class TemporalSplitConfig:
    train_start: date
    train_end: date
    holdout_start: date
    holdout_end: date

    @property
    def window_days(self) -> int:
        return (self.holdout_end - self.train_start).days + 1


@dataclass
class SynthConfig:
    version: str
    frozen_at: str | None
    reference_date: date
    categories: list[CategoryConfig]
    calibration: CalibrationConfig
    districts: list[str]
    household_size_weights: dict[int, float]
    chains: list[ChainConfig]
    segments: list[SegmentConfig]
    category_economics: list[CategoryEconomicsConfig]
    forbidden_categories: list[str]
    temporal_split: TemporalSplitConfig

    def all_items(self) -> list[tuple[str, str]]:
        """Return (category_name, item_name) pairs for every item in the schema."""
        return [(c.name, item) for c in self.categories for item in c.items]


def load_config(path: str | Path) -> SynthConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    categories = [
        CategoryConfig(name=c["name"], items=list(c["items"]))
        for c in raw["categories"]
    ]
    calibration = CalibrationConfig(**raw["calibration"])
    household_size_weights = {
        int(k): float(v) for k, v in raw["household_size_weights"].items()
    }
    chains = [
        ChainConfig(
            name=c["name"],
            price_multiplier=float(c["price_multiplier"]),
            segment_weights={k: float(v) for k, v in c["segment_weights"].items()},
        )
        for c in raw["chains"]
    ]
    segments = [
        SegmentConfig(
            name=s["name"],
            visit_frequency_multiplier=float(s["visit_frequency_multiplier"]),
            basket_size_multiplier=float(s["basket_size_multiplier"]),
        )
        for s in raw["segments"]
    ]
    category_economics = [
        CategoryEconomicsConfig(
            category=e["category"],
            base_price_rub=float(e["base_price_rub"]),
            price_jitter_pct=float(e["price_jitter_pct"]),
            margin_pct=float(e["margin_pct"]),
            popularity_weight=float(e["popularity_weight"]),
        )
        for e in raw["category_economics"]
    ]
    ts = raw["temporal_split"]
    temporal_split = TemporalSplitConfig(
        train_start=date.fromisoformat(str(ts["train_start"])),
        train_end=date.fromisoformat(str(ts["train_end"])),
        holdout_start=date.fromisoformat(str(ts["holdout_start"])),
        holdout_end=date.fromisoformat(str(ts["holdout_end"])),
    )

    return SynthConfig(
        version=raw["version"],
        frozen_at=raw.get("frozen_at"),
        reference_date=date.fromisoformat(raw["reference_date"]),
        categories=categories,
        calibration=calibration,
        districts=list(raw["districts"]),
        household_size_weights=household_size_weights,
        chains=chains,
        segments=segments,
        category_economics=category_economics,
        forbidden_categories=list(raw["forbidden_categories"]),
        temporal_split=temporal_split,
    )
