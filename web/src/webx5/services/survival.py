from __future__ import annotations

from datetime import date

from synth.survival import SurvivalCurve, fit_population_curves

from webx5.crud.survival import SurvivalRepository
from webx5.database.database import Database


class SurvivalCurveStore:
    """Population-level Kaplan-Meier category-risk curves.

    Fetching is lazy (on first `.curves` access, not at construction), while
    `refresh()` rebuilds the model from the latest receipts before a new
    challenge batch. This keeps import-time wiring free of DB connections and
    ensures a completed challenge can affect the next model fit.
    """

    def __init__(self, db: Database, repo: SurvivalRepository | None = None) -> None:
        self._db = db
        self._repo = repo if repo is not None else SurvivalRepository()
        self._curves: dict[str, SurvivalCurve] | None = None

    @property
    def curves(self) -> dict[str, SurvivalCurve]:
        if self._curves is None:
            return self.refresh()
        return self._curves

    def refresh(self) -> dict[str, SurvivalCurve]:
        """Refit all population curves from the current DB state."""
        with self._db.get_sync_session() as session:
            purchase_dates = self._repo.fetch_purchase_dates(session)
        self._curves = fit_population_curves(purchase_dates, as_of=date.today())  # noqa: DTZ011
        return self._curves
