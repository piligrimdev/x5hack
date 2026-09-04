"""Lazy singleton for `forbidden_categories` from the shared synth config.

Single source of truth with `synth/challenges.py` — both read from the same
`config/synth_schema.yaml`. Path from env `SYNTH_CONFIG_PATH`.
"""

from __future__ import annotations

import os
from functools import lru_cache

from synth.config import load_config


@lru_cache(maxsize=1)
def get_forbidden_categories() -> frozenset[str]:
    path = os.environ.get("SYNTH_CONFIG_PATH", "/config/synth_schema.yaml")
    config = load_config(path)
    return frozenset(config.forbidden_categories)


@lru_cache(maxsize=1)
def get_synth_config():
    """Cached SynthConfig — used both for forbidden_categories and by the
    challenge generation adapter (categories, category_economics, etc.)."""
    path = os.environ.get("SYNTH_CONFIG_PATH", "/config/synth_schema.yaml")
    return load_config(path)
