from __future__ import annotations

from datetime import date

from synth.survival import SurvivalCurve, fit_population_curves

from webx5.crud.survival import SurvivalRepository
from webx5.database.database import Database


class SurvivalCurveStore:
    """Population-level Kaplan-Meier category-risk curves, fit once per
    process and cached in memory for its whole life — no TTL/periodic
    refresh (see `docs/superpowers/specs/2026-09-06-challenge-survival-risk-design.md`
    §2 for why). Fetching is lazy (on first `.curves` access, not at
    construction) so building this object never opens a DB connection by
    itself — `core/challenges.py`, which constructs it, must not gain a
    DB call at import time.
    """

    def __init__(self, db: Database, repo: SurvivalRepository | None = None) -> None:
        self._db = db
        self._repo = repo if repo is not None else SurvivalRepository()
        self._curves: dict[str, SurvivalCurve] | None = None

    @property
    def curves(self) -> dict[str, SurvivalCurve]:
        if self._curves is None:
            with self._db.get_sync_session() as session:
                purchase_dates = self._repo.fetch_purchase_dates(session)
            self._curves = fit_population_curves(purchase_dates, as_of=date.today())  # noqa: DTZ011
        return self._curves
