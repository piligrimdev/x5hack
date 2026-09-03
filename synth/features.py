from __future__ import annotations

from synth.config import SynthConfig
from synth.receipts import Receipt


def compute_observable_habitual_categories(
    receipts: list[Receipt], config: SynthConfig, top_k: int = 5
) -> list[str]:
    """Derive the OBSERVABLE `habitual_categories` field from TRAIN-period
    receipts only.

    This is deliberately different from the hidden generation-time bias
    list used to shape category sampling (see `synth/simulation_truth.py`'s
    `category_affinity`) — that list encodes the "true" generative intent;
    this function re-derives a recommender-visible signal purely from what
    a recommender could actually observe (train-period purchase history),
    which is the only leakage-safe way to populate this field once a
    train/holdout split exists (spec requirement: "не допускай утечки
    holdout").
    """
    train_end = config.temporal_split.train_end.isoformat()
    counts: dict[str, int] = {}
    for r in receipts:
        if r.purchase_date > train_end:
            continue
        for line in r.lines:
            counts[line.category] = counts.get(line.category, 0) + 1

    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [cat for cat, _ in ranked[:top_k]]
