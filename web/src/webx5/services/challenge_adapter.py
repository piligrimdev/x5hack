"""Impedance-mismatch layer between the ORM (Task/Receipt/Product/Category/etc.)
and the pure-function synth generator (`synth.challenges.generate_challenge_for_user`).

Responsibilities:
  * `build_profile(session, user_id)` — ORM → dict-profile that `synth` expects
  * `_lookup_product(session, item_name, category_id)` — resolve item string → Product row
  * `persist_challenge(session, user_id, script_result)` → Task + TaskCriterion rows

Mapping of extra criterion fields from script output → task_criterion.kind uses
`SCRIPT_FIELD_TO_CRITERION_KIND` — see research.md R11 for the "extend LLM schema
without a migration" contract.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from synth.challenges import pick_vibe_category
from synth.config import SynthConfig
from webx5.crud.task import TaskRepository
from webx5.entities.category import Category
from webx5.entities.product import Product
from webx5.entities.receipt import Receipt, ReceiptItem
from webx5.entities.user import User

# Map: field name in the script's result dict → task_criterion.kind string.
# When a new field appears in the LLM JSON schema (added by another dev),
# add a single line here to persist it as an additional criterion.
# Completion checker in services/task_completion.py must ALSO know the kind,
# otherwise the task is treated as never-completable (FR-024 safety).
SCRIPT_FIELD_TO_CRITERION_KIND: dict[str, str] = {
    "spend_threshold_rub": "spend_threshold_rub",
}


class ChallengeAdapter:
    def __init__(self, task_repo: TaskRepository) -> None:
        self.task_repo = task_repo

    # ------- vibe-of-the-month resolution -------
    def _resolve_vibe_category(self, session: Session, user: User) -> str:
        """Return this user's "vibe" theme for the current calendar month.
        Stable across generation calls within a month; auto-rotates at the
        start of each new month via `pick_vibe_category` until a future
        manual-selection feature lets a user pick their own — the
        `vibe_category`/`vibe_month` columns exist for that reason, not
        just as a cache."""
        month_start = date.today().replace(day=1)
        if user.vibe_category and user.vibe_month == month_start:
            return user.vibe_category
        vibe_category = pick_vibe_category(str(user.id), month_start.strftime("%Y-%m"))
        user.vibe_category = vibe_category
        user.vibe_month = month_start
        session.flush()
        return vibe_category

    # ------- ORM → dict-profile for synth --------
    def build_profile(self, session: Session, user_id: uuid.UUID, config: SynthConfig) -> dict:
        """Assemble the dict shape `synth.challenges.generate_challenge_for_user` expects.

        Only real fields sourced from the DB; margin per line is synthesized
        from `config.category_economics` because production DB doesn't store margin.

        May assign and persist a new `vibe_category`/`vibe_month` on the
        user's row via `_resolve_vibe_category` — this method is not
        read-only despite its name.
        """
        user: User | None = session.get(User, user_id)
        if user is None:
            raise ValueError(f"User not found: {user_id}")

        vibe_category = self._resolve_vibe_category(session, user)

        # Read last 90 days of receipts for this user.
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        rows = (
            session.execute(
                select(Receipt)
                .where(Receipt.loyalty_card_id == user_id, Receipt.purchase_date >= cutoff)
                .order_by(Receipt.purchase_date.asc())
            )
            .scalars()
            .all()
        )

        econ_by_category = {e.category: e for e in config.category_economics}

        receipts_dicts: list[dict] = []
        habit_counter: Counter = Counter()
        for r in rows:
            lines: list[dict] = []
            total_rub = Decimal("0")
            items = session.execute(
                select(ReceiptItem, Product, Category)
                .join(Product, ReceiptItem.product_id == Product.id)
                .join(Category, Product.category_id == Category.id)
                .where(ReceiptItem.receipt_id == r.id)
            ).all()
            for ri, product, category in items:
                cat_name = category.name
                habit_counter[cat_name] += 1
                base_price = Decimal(str(ri.base_price_at_purchase))
                paid_price = Decimal(str(ri.paid_price))
                margin_pct = Decimal(str(econ_by_category[cat_name].margin_pct)) if cat_name in econ_by_category else Decimal("15")
                # Approximated margin per unit — enough for `estimate_max_reward_rub`.
                gross_margin = (paid_price * margin_pct / Decimal("100")).quantize(Decimal("0.01"))
                on_promo = ri.discount_id is not None
                lines.append({
                    "category": cat_name,
                    "item": product.name,
                    "regular_unit_price_rub": float(base_price),
                    "paid_price_rub": float(paid_price),
                    "gross_margin_rub": float(gross_margin),
                    "qty": int(ri.quantity),
                    "on_promo": on_promo,
                })
                total_rub += paid_price * Decimal(int(ri.quantity))
            receipts_dicts.append({
                "receipt_id": str(r.id),
                "purchase_date": r.purchase_date.date().isoformat(),
                "channel": r.channel,
                "total_rub": float(total_rub),
                "lines": lines,
            })

        # Top-5 categories are the "habitual" list (matches synth's schema).
        habitual = [cat for cat, _ in habit_counter.most_common(5)]

        # Chain / segment are not tracked in the current schema — pass placeholders.
        return {
            "user_id": str(user_id),
            "chain": "Пятёрочка",
            "segment": "unknown",
            "family_size": 1,
            "habitual_categories": habitual,
            "receipts": receipts_dicts,
            "vibe_category": vibe_category,
        }

    # ------- Product resolution -------
    def _lookup_product(
        self, session: Session, item_name: str, category_id: uuid.UUID
    ) -> Product | None:
        return session.execute(
            select(Product)
            .where(Product.category_id == category_id, Product.name.ilike(f"%{item_name}%"))
            .order_by(func.char_length(Product.name).asc())
            .limit(1)
        ).scalar_one_or_none()

    def _resolve_category(self, session: Session, name: str) -> Category | None:
        return session.execute(select(Category).where(Category.name == name)).scalar_one_or_none()

    def _lookup_product_by_sku(self, session: Session, sku_id: str) -> Product | None:
        return session.execute(select(Product).where(Product.sku_id == sku_id)).scalar_one_or_none()

    # ------- criterion resolution (no writes) -------
    def resolve_criterion(self, session: Session, script_result: dict) -> tuple[str, uuid.UUID]:
        """Resolve the `(criterion_type, criterion_entity_id)` pair a
        script_result WOULD persist to, without creating any rows.

        Used by `ChallengeService.generate_batch` to detect, before calling
        `persist_challenge`, whether a slot would create a Task with the same
        criterion pair as another slot in this batch or an already-active
        task (e.g. `vibe` and `llm_habit` both landing on the same category)
        — and reused by `persist_challenge` itself below, so the resolution
        logic (target_sku_id → product lookup → category fallback) lives in
        exactly one place.

        Raises `ValueError` for the same reasons `persist_challenge` would
        refuse to build a task: missing `target_categories`, or a category
        name that isn't in the DB.
        """
        target_categories = script_result.get("target_categories") or []
        if not target_categories:
            raise ValueError("script_result missing target_categories")

        primary_category_name = target_categories[0]
        category = self._resolve_category(session, primary_category_name)
        if category is None:
            raise ValueError(f"Category not found in DB: {primary_category_name}")

        # Prefer target_sku_id (deterministic SKU picked by the script);
        # fall back to fuzzy item-name lookup (favorite_item / novel_item);
        # finally fall back to category-level criterion.
        product: Product | None = None
        target_sku_id = script_result.get("target_sku_id")
        if target_sku_id:
            product = self._lookup_product_by_sku(session, str(target_sku_id))

        if product is None:
            item_name = script_result.get("favorite_item") or script_result.get("novel_item")
            if item_name:
                product = self._lookup_product(session, item_name, category.id)

        if product is not None:
            return "product", product.id
        return "category", category.id

    # ------- dict-result → Task + TaskCriterion rows -------
    def persist_challenge(
        self,
        session: Session,
        user_id: uuid.UUID,
        script_result: dict,
    ) -> uuid.UUID:
        """Map one non-'no_challenge' script result to a Task + TaskCriterion rows.
        Returns the new task's id.
        """
        criterion_type, criterion_entity_id = self.resolve_criterion(session, script_result)

        # Reward amount — clamp to non-negative.
        reward_rub = Decimal(str(script_result.get("reward_rub", 0)))
        if reward_rub < Decimal("0"):
            reward_rub = Decimal("0")

        # Quantity from the script (LLM extension: `quantity`; older name: `quantity_target`;
        # new deterministic paths / LLM slot: `target_quantity` — accept any).
        raw_qty = (
            script_result.get("quantity")
            or script_result.get("target_quantity")
            or script_result.get("quantity_target")
            or 1
        )
        try:
            qty_target = int(raw_qty)
        except (TypeError, ValueError):
            qty_target = 1
        if qty_target < 1:
            qty_target = 1

        task = self.task_repo.create(
            session,
            loyalty_card_id=user_id,
            criterion_type=criterion_type,
            criterion_entity_id=criterion_entity_id,
            quantity_target=qty_target,
            title=str(script_result.get("challenge_title", "Challenge")),
            description=str(script_result.get("description", "")),
            mechanic=str(script_result.get("mechanic", "")),
            reward_rub=reward_rub,
            reasoning=script_result.get("reasoning"),
            path=str(script_result.get("path", "personal")),
            model=script_result.get("model"),
            challenge_slot=script_result.get("challenge_slot"),
        )

        # Base criterion: item_quantity mirrors task.quantity_target.
        self.task_repo.create_criterion(
            session,
            task_id=task.id,
            kind="item_quantity",
            value_num=Decimal(qty_target),
        )

        # Additional criteria — from script fields via the extension map.
        for script_field, kind in SCRIPT_FIELD_TO_CRITERION_KIND.items():
            if script_field in script_result and script_result[script_field] is not None:
                raw_value = script_result[script_field]
                if isinstance(raw_value, (int, float, Decimal)):
                    self.task_repo.create_criterion(
                        session,
                        task_id=task.id,
                        kind=kind,
                        value_num=Decimal(str(raw_value)),
                    )
                else:
                    self.task_repo.create_criterion(
                        session,
                        task_id=task.id,
                        kind=kind,
                        value_text=str(raw_value),
                    )

        return task.id
