# Превью цены/скидки в корзине, баллы, навигация — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В корзине на неделю видно цену и цену со скидкой на товар, можно списать баллы лояльности при оформлении заказа, а нижний таб-бар «Корзина» открывает экран с корзиной.

**Architecture:** Новый метод `BasketService.preview()` и эндпоинт `POST /basket/preview` переиспользуют уже существующие `DiscountCalculatorService.calculate()` и `PointsService.preview_for_calculate()`, отдавая уже существующую схему `CalculateResponse` (ту же, что использует терминальный `/receipts/calculate`) — новой персистентности и почти новых типов нет. Логика выбора магазина, продублированная между `checkout()` и новым `preview()`, выносится в приватный `_resolve_store()`. `points_to_spend` прокидывается в уже существующую логику списания баллов внутри `create_receipt`. Прогресс в челленджи при покупке уже работает сегодня (тот же `create_receipt` → Celery `process_receipt`) — в этом плане не трогается.

**Tech Stack:** FastAPI + SQLAlchemy (sync), Pydantic v2 (бэкенд `web/src/webx5`); Expo/React Native/TypeScript (фронт `x5mobile/`).

**Spec:** [docs/superpowers/specs/2026-09-05-basket-preview-points-nav-design.md](../specs/2026-09-05-basket-preview-points-nav-design.md)

## Global Constraints

- RSI-слои: routes = schema + session → service; вся бизнес-логика в services; никакого SQL в routes.
- DI: сервис получает зависимости через конструктор, не создаёт их сам.
- Новых таблиц/миграций в этой фиче нет.
- `POST /basket/preview` и `POST /basket/checkout` — `CurrentUserUUID` auth, НЕ `TerminalTokenDep`.
- Превью пустой корзины — валидный случай (не 422), в отличие от чекаута пустой корзины.
- Списание баллов — только вкл/выкл (`points_to_spend: "all" | None`), без ввода точного количества (вне объёма).
- Прогресс в челленджи при покупке из корзины уже работает — код не трогать, не тестировать заново.
- Тесты бэкенда: `poetry -C web run pytest` (если `poetry` не в PATH — `python3 -m poetry -C web run pytest`; для тестов, импортирующих `synth`, нужен `PYTHONPATH=<repo-root>`).
- У фронта (`x5mobile/`) нет тестового фреймворка — верификация фронтенд-задач ручная (curl + запуск в браузере/симуляторе).

---

### Task 1: `BasketService._resolve_store()` + `POST /basket/preview`

**Files:**
- Modify: `web/src/webx5/services/basket_assistant.py`
- Modify: `web/src/webx5/core/basket.py`
- Modify: `web/src/webx5/schemas/basket.py`
- Modify: `web/src/webx5/routes/basket.py`
- Test: `web/tests/webx5/services/test_basket_assistant.py`
- Test: `web/tests/webx5/routes/test_basket.py`

**Interfaces:**
- Consumes: `DiscountCalculatorService.calculate(items, store, loyalty_card_id, session) -> list[CalculatedItem]` (уже существует). `PointsService.preview_for_calculate(session, loyalty_card_id, points_requested_raw, subtotal_rub) -> CashbackPreview | None` (уже существует, `web/src/webx5/services/points.py:150`). `ReceiptRepository.list_by_loyalty_card`, `StoreRepository.get_by_id`/`list_all` (уже существуют).
- Produces: `BasketService._resolve_store(session, user_id) -> Store` (приватный, переиспользуется `checkout()` этой же задачей). `BasketService.preview(session, user_id, items, points_to_spend=None) -> CalculateResponse` — используется Task 3's фронтенд-хук через новый роут.

- [ ] **Step 1: Write the failing tests**

Добавь в `web/tests/webx5/services/test_basket_assistant.py` новый фикстур (рядом с существующими `repo`/`receipt_repo`/`store_repo`/`discount_calc`/`receipt_service`):

```python
from webx5.services.points import CashbackPreview, PointsService


@pytest.fixture()
def points_service() -> MagicMock:
    return MagicMock(spec=PointsService)
```

Обнови фикстуру `service`, добавив `points_service`:

```python
@pytest.fixture()
def service(
    repo: MagicMock,
    receipt_repo: MagicMock,
    store_repo: MagicMock,
    discount_calc: MagicMock,
    receipt_service: MagicMock,
    points_service: MagicMock,
) -> BasketService:
    return BasketService(
        repo=repo,
        receipt_repo=receipt_repo,
        store_repo=store_repo,
        discount_calc=discount_calc,
        receipt_service=receipt_service,
        points_service=points_service,
        model="fake/model",
    )
```

Добавь в конец файла:

```python
class TestPreview:
    def test_returns_priced_items_with_discount_and_cashback(
        self,
        service: BasketService,
        repo: MagicMock,
        receipt_repo: MagicMock,
        store_repo: MagicMock,
        discount_calc: MagicMock,
        points_service: MagicMock,
        session: MagicMock,
    ) -> None:
        milk = _make_product("sku_0001", "Молоко", price="100.00")
        repo.get_full_catalog.return_value = [milk]

        store = _make_store()
        last_receipt = MagicMock(store_id=store.id)
        receipt_repo.list_by_loyalty_card.return_value = ([last_receipt], 1)
        store_repo.get_by_id.return_value = store

        discount_calc.calculate.return_value = [
            CalculatedItem(
                product_id=milk.id,
                product_name=milk.name,
                quantity=2,
                base_price=Decimal("100.00"),
                paid_price=Decimal("90.00"),
                discount_id=uuid.uuid4(),
                discounted_amount=Decimal("10.00"),
            )
        ]
        points_service.preview_for_calculate.return_value = CashbackPreview(
            points_available=500,
            points_to_apply=0,
            cashback_rub=0,
            total_paid_rub=180,
            points_balance_after=500,
            points_capped_by="none",
            rate_points_per_rub=10,
        )

        user_id = uuid.uuid4()
        result = service.preview(session, user_id, [BasketItemIn(product_id=milk.id, quantity=2)])

        assert result.store_id == store.id
        assert result.items[0].base_price == Decimal("100.00")
        assert result.items[0].paid_price == Decimal("90.00")
        assert result.total_base == Decimal("200.00")
        assert result.total_paid == Decimal("180.00")
        assert result.total_saved == Decimal("20.00")
        assert result.cashback is not None
        assert result.cashback.points_available == 500
        points_service.preview_for_calculate.assert_called_once_with(
            session, loyalty_card_id=user_id, points_requested_raw=None, subtotal_rub=180
        )

    def test_empty_basket_returns_zero_totals_not_422(
        self,
        service: BasketService,
        repo: MagicMock,
        receipt_repo: MagicMock,
        store_repo: MagicMock,
        discount_calc: MagicMock,
        points_service: MagicMock,
        session: MagicMock,
    ) -> None:
        repo.get_full_catalog.return_value = []
        store = _make_store()
        receipt_repo.list_by_loyalty_card.return_value = ([], 0)
        store_repo.list_all.return_value = [store]
        discount_calc.calculate.return_value = []
        points_service.preview_for_calculate.return_value = None

        result = service.preview(session, uuid.uuid4(), [])

        assert result.items == []
        assert result.total_base == Decimal("0")
        assert result.total_paid == Decimal("0")
        assert result.cashback is None

    def test_unknown_product_id_raises_422(
        self, service: BasketService, repo: MagicMock, session: MagicMock
    ) -> None:
        repo.get_full_catalog.return_value = []
        with pytest.raises(HTTPException) as exc_info:
            service.preview(session, uuid.uuid4(), [BasketItemIn(product_id=uuid.uuid4(), quantity=1)])
        assert exc_info.value.status_code == 422

    def test_points_to_spend_forwarded_to_points_service(
        self,
        service: BasketService,
        repo: MagicMock,
        receipt_repo: MagicMock,
        store_repo: MagicMock,
        discount_calc: MagicMock,
        points_service: MagicMock,
        session: MagicMock,
    ) -> None:
        repo.get_full_catalog.return_value = []
        receipt_repo.list_by_loyalty_card.return_value = ([], 0)
        store_repo.list_all.return_value = [_make_store()]
        discount_calc.calculate.return_value = []
        points_service.preview_for_calculate.return_value = None

        service.preview(session, uuid.uuid4(), [], points_to_spend="all")

        assert points_service.preview_for_calculate.call_args.kwargs["points_requested_raw"] == "all"


class TestResolveStoreViaCheckout:
    """checkout() must keep working unchanged after the _resolve_store extraction."""

    def test_checkout_still_uses_last_receipt_store(
        self,
        service: BasketService,
        repo: MagicMock,
        receipt_repo: MagicMock,
        store_repo: MagicMock,
        discount_calc: MagicMock,
        receipt_service: MagicMock,
        session: MagicMock,
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        store = _make_store()
        last_receipt = MagicMock(store_id=store.id)
        receipt_repo.list_by_loyalty_card.return_value = ([last_receipt], 1)
        store_repo.get_by_id.return_value = store
        discount_calc.calculate.return_value = [
            CalculatedItem(
                product_id=milk.id, product_name=milk.name, quantity=1,
                base_price=Decimal("50.00"), paid_price=Decimal("50.00"),
                discount_id=None, discounted_amount=Decimal("0.00"),
            )
        ]
        receipt_service.create_receipt.return_value = (MagicMock(), True)

        service.checkout(session, uuid.uuid4(), [BasketItemIn(product_id=milk.id, quantity=1)])

        store_repo.get_by_id.assert_called_once_with(session, store.id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry -C web run pytest tests/webx5/services/test_basket_assistant.py -v`
Expected: FAIL — `TypeError: BasketService.__init__() got an unexpected keyword argument 'points_service'`.

- [ ] **Step 3: Implement `_resolve_store` + `preview`**

In `web/src/webx5/services/basket_assistant.py`, update the imports block:

```python
from __future__ import annotations

import uuid
from decimal import Decimal

import structlog
from fastapi import HTTPException
from sqlalchemy.orm import Session

from webx5.core.llm import call_openrouter_tools
from webx5.crud.basket import BasketRepository
from webx5.crud.receipt import ReceiptRepository
from webx5.crud.store import StoreRepository
from webx5.entities.product import Product
from webx5.schemas.basket import AssistantResponse, BasketItem, BasketItemIn
from webx5.schemas.receipt import ReceiptCreate, ReceiptItemCreate, ReceiptResponse
from webx5.services.discount_calculator import CartItem, DiscountCalculatorService
from webx5.services.receipt import ReceiptService
```

to:

```python
from __future__ import annotations

import uuid
from decimal import Decimal

import structlog
from fastapi import HTTPException
from sqlalchemy.orm import Session

from webx5.core.llm import call_openrouter_tools
from webx5.crud.basket import BasketRepository
from webx5.crud.receipt import ReceiptRepository
from webx5.crud.store import StoreRepository
from webx5.entities.product import Product
from webx5.entities.store import Store
from webx5.schemas.basket import AssistantResponse, BasketItem, BasketItemIn
from webx5.schemas.receipt import (
    CalculatedItemOut,
    CalculateResponse,
    CashbackBlock,
    PointsToSpend,
    ReceiptCreate,
    ReceiptItemCreate,
    ReceiptResponse,
)
from webx5.services.discount_calculator import CartItem, DiscountCalculatorService
from webx5.services.points import PointsService
from webx5.services.receipt import ReceiptService
```

Update `__init__` — replace:

```python
    def __init__(
        self,
        repo: BasketRepository,
        receipt_repo: ReceiptRepository,
        store_repo: StoreRepository,
        discount_calc: DiscountCalculatorService,
        receipt_service: ReceiptService,
        model: str = "anthropic/claude-haiku-4.5",
    ) -> None:
        self.repo = repo
        self.receipt_repo = receipt_repo
        self.store_repo = store_repo
        self.discount_calc = discount_calc
        self.receipt_service = receipt_service
        self.model = model
```

with:

```python
    def __init__(
        self,
        repo: BasketRepository,
        receipt_repo: ReceiptRepository,
        store_repo: StoreRepository,
        discount_calc: DiscountCalculatorService,
        receipt_service: ReceiptService,
        points_service: PointsService,
        model: str = "anthropic/claude-haiku-4.5",
    ) -> None:
        self.repo = repo
        self.receipt_repo = receipt_repo
        self.store_repo = store_repo
        self.discount_calc = discount_calc
        self.receipt_service = receipt_service
        self.points_service = points_service
        self.model = model
```

Replace the store-resolution block inside `checkout()` — find:

```python
        receipts, _total = self.receipt_repo.list_by_loyalty_card(session, user_id, page=1, size=1)
        if receipts:
            store = self.store_repo.get_by_id(session, receipts[0].store_id)
        else:
            stores = self.store_repo.list_all(session)
            if not stores:
                raise HTTPException(status_code=422, detail=CHECKOUT_NO_STORES_MESSAGE)
            store = stores[0]

        cart_items = [CartItem(product_id=i.product_id, quantity=i.quantity) for i in items]
```

replace with:

```python
        store = self._resolve_store(session, user_id)

        cart_items = [CartItem(product_id=i.product_id, quantity=i.quantity) for i in items]
```

Add the new `_resolve_store` and `preview` methods right after `checkout()` (before `_build_system_prompt`):

```python
    def _resolve_store(self, session: Session, user_id: uuid.UUID) -> Store:
        receipts, _total = self.receipt_repo.list_by_loyalty_card(session, user_id, page=1, size=1)
        if receipts:
            return self.store_repo.get_by_id(session, receipts[0].store_id)
        stores = self.store_repo.list_all(session)
        if not stores:
            raise HTTPException(status_code=422, detail=CHECKOUT_NO_STORES_MESSAGE)
        return stores[0]

    def preview(
        self,
        session: Session,
        user_id: uuid.UUID,
        items: list[BasketItemIn],
        points_to_spend: PointsToSpend = None,
    ) -> CalculateResponse:
        catalog = self.repo.get_full_catalog(session)
        catalog_by_id = {p.id: p for p in catalog}
        missing = [str(i.product_id) for i in items if i.product_id not in catalog_by_id]
        if missing:
            raise HTTPException(
                status_code=422,
                detail={"detail": "Unknown product_ids", "unknown_product_ids": missing},
            )

        store = self._resolve_store(session, user_id)

        cart_items = [CartItem(product_id=i.product_id, quantity=i.quantity) for i in items]
        calculated = self.discount_calc.calculate(
            items=cart_items, store=store, loyalty_card_id=user_id, session=session
        )
        items_out = [
            CalculatedItemOut(
                product_id=c.product_id,
                product_name=c.product_name,
                quantity=c.quantity,
                base_price=c.base_price,
                paid_price=c.paid_price,
                discount_id=c.discount_id,
                discounted_amount=c.discounted_amount,
            )
            for c in calculated
        ]
        total_base = sum((i.base_price * i.quantity for i in items_out), Decimal("0"))
        total_paid = sum((i.paid_price * i.quantity for i in items_out), Decimal("0"))

        cashback = self.points_service.preview_for_calculate(
            session,
            loyalty_card_id=user_id,
            points_requested_raw=points_to_spend,
            subtotal_rub=int(total_paid),
        )
        cashback_block = (
            CashbackBlock(
                points_available=cashback.points_available,
                points_to_apply=cashback.points_to_apply,
                cashback_rub=cashback.cashback_rub,
                total_paid_rub=cashback.total_paid_rub,
                points_balance_after=cashback.points_balance_after,
                points_capped_by=cashback.points_capped_by,
                rate_points_per_rub=cashback.rate_points_per_rub,
            )
            if cashback is not None
            else None
        )

        return CalculateResponse(
            store_id=store.id,
            loyalty_card_id=user_id,
            items=items_out,
            total_base=total_base,
            total_paid=total_paid,
            total_saved=(total_base - total_paid) + (cashback_block.cashback_rub if cashback_block else 0),
            cashback=cashback_block,
        )
```

Now update `web/src/webx5/core/basket.py`. Current content:

```python
import os

from webx5.core.purchases import discount_calculator_service, receipt_repo, receipt_service
from webx5.crud.basket import BasketRepository
from webx5.crud.store import StoreRepository
from webx5.services.basket_assistant import BasketService

BASKET_LLM_MODEL = os.environ.get("BASKET_LLM_MODEL", "anthropic/claude-haiku-4.5")

basket_repo = BasketRepository()
basket_service = BasketService(
    repo=basket_repo,
    receipt_repo=receipt_repo,
    store_repo=StoreRepository(),
    discount_calc=discount_calculator_service,
    receipt_service=receipt_service,
    model=BASKET_LLM_MODEL,
)
```

replace with:

```python
import os

from webx5.core.points import points_service
from webx5.core.purchases import discount_calculator_service, receipt_repo, receipt_service
from webx5.crud.basket import BasketRepository
from webx5.crud.store import StoreRepository
from webx5.services.basket_assistant import BasketService

BASKET_LLM_MODEL = os.environ.get("BASKET_LLM_MODEL", "anthropic/claude-haiku-4.5")

basket_repo = BasketRepository()
basket_service = BasketService(
    repo=basket_repo,
    receipt_repo=receipt_repo,
    store_repo=StoreRepository(),
    discount_calc=discount_calculator_service,
    receipt_service=receipt_service,
    points_service=points_service,
    model=BASKET_LLM_MODEL,
)
```

Add the new request schema to `web/src/webx5/schemas/basket.py` — append after `CheckoutRequest`:

```python
class BasketPreviewRequest(BaseModel):
    items: list[BasketItemIn]
    points_to_spend: PointsToSpend = None
```

Add the import it needs at the top of `web/src/webx5/schemas/basket.py`:

```python
from webx5.schemas.receipt import PointsToSpend
```

- [ ] **Step 4: Add the route**

In `web/src/webx5/routes/basket.py`, update imports:

```python
from webx5.schemas.basket import (
    AssistantRequest,
    AssistantResponse,
    CheckoutRequest,
    SuggestedBasketResponse,
)
from webx5.schemas.receipt import ReceiptResponse
```

to:

```python
from webx5.schemas.basket import (
    AssistantRequest,
    AssistantResponse,
    BasketPreviewRequest,
    CheckoutRequest,
    SuggestedBasketResponse,
)
from webx5.schemas.receipt import CalculateResponse, ReceiptResponse
```

Add the new route after `get_suggested_basket` (before `post_basket_assistant`):

```python
@basket_router.post("/preview", response_model=CalculateResponse)
def post_basket_preview(
    data: BasketPreviewRequest,
    session: SessionDep,
    user_id: CurrentUserUUID,
) -> CalculateResponse:
    from webx5.core.basket import basket_service

    return basket_service.preview(session, user_id, data.items, data.points_to_spend)
```

Add a route-level test to `web/tests/webx5/routes/test_basket.py` — append:

```python
class TestPostBasketPreview:
    def test_returns_priced_preview(self) -> None:
        from webx5.schemas.receipt import CalculatedItemOut, CalculateResponse

        fake_response = CalculateResponse(
            store_id=uuid.uuid4(),
            loyalty_card_id=uuid.uuid4(),
            items=[
                CalculatedItemOut(
                    product_id=uuid.uuid4(),
                    product_name="Молоко",
                    quantity=2,
                    base_price=Decimal("100.00"),
                    paid_price=Decimal("90.00"),
                    discount_id=None,
                    discounted_amount=Decimal("10.00"),
                )
            ],
            total_base=Decimal("200.00"),
            total_paid=Decimal("180.00"),
            total_saved=Decimal("20.00"),
            cashback=None,
        )
        with patch(
            "webx5.services.basket_assistant.BasketService.preview",
            return_value=fake_response,
        ):
            resp = client.post(
                "/basket/preview",
                json={"items": [{"product_id": str(uuid.uuid4()), "quantity": 2}]},
                headers=_bearer(_token()),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_saved"] == 20.0
        assert body["items"][0]["paid_price"] == 90.0

    def test_requires_auth(self) -> None:
        resp = client.post("/basket/preview", json={"items": []})
        assert resp.status_code == 401

    def test_empty_items_is_valid_request(self) -> None:
        from webx5.schemas.receipt import CalculateResponse

        fake_response = CalculateResponse(
            store_id=uuid.uuid4(),
            loyalty_card_id=uuid.uuid4(),
            items=[],
            total_base=Decimal("0"),
            total_paid=Decimal("0"),
            total_saved=Decimal("0"),
            cashback=None,
        )
        with patch(
            "webx5.services.basket_assistant.BasketService.preview",
            return_value=fake_response,
        ):
            resp = client.post("/basket/preview", json={"items": []}, headers=_bearer(_token()))
        assert resp.status_code == 200
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry -C web run pytest tests/webx5/services/test_basket_assistant.py tests/webx5/routes/test_basket.py -v`
Expected: PASS, all tests in both files (old + new) green.

- [ ] **Step 6: Commit**

```bash
git add web/src/webx5/services/basket_assistant.py web/src/webx5/core/basket.py web/src/webx5/schemas/basket.py web/src/webx5/routes/basket.py web/tests/webx5/services/test_basket_assistant.py web/tests/webx5/routes/test_basket.py
git commit -m "feat: add BasketService.preview and POST /basket/preview endpoint"
```

---

### Task 2: `points_to_spend` on checkout

**Files:**
- Modify: `web/src/webx5/schemas/basket.py`
- Modify: `web/src/webx5/services/basket_assistant.py`
- Modify: `web/src/webx5/routes/basket.py`
- Test: `web/tests/webx5/services/test_basket_assistant.py`
- Test: `web/tests/webx5/routes/test_basket.py`

**Interfaces:**
- Consumes: `ReceiptCreate.points_to_spend: PointsToSpend` (already exists, already handled inside `ReceiptService.create_receipt`, unchanged in this task).
- Produces: `BasketService.checkout(session, user_id, items, points_to_spend=None) -> ReceiptResponse` — the new optional 4th parameter is used by Task 3's frontend.

- [ ] **Step 1: Write the failing test**

Add to `web/tests/webx5/services/test_basket_assistant.py`'s `TestCheckout` class:

```python
    def test_points_to_spend_forwarded_to_receipt_create(
        self,
        service: BasketService,
        repo: MagicMock,
        receipt_repo: MagicMock,
        store_repo: MagicMock,
        discount_calc: MagicMock,
        receipt_service: MagicMock,
        session: MagicMock,
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        store = _make_store()
        receipt_repo.list_by_loyalty_card.return_value = ([], 0)
        store_repo.list_all.return_value = [store]
        discount_calc.calculate.return_value = [
            CalculatedItem(
                product_id=milk.id, product_name=milk.name, quantity=1,
                base_price=Decimal("100.00"), paid_price=Decimal("100.00"),
                discount_id=None, discounted_amount=Decimal("0.00"),
            )
        ]
        receipt_service.create_receipt.return_value = (MagicMock(), True)

        service.checkout(
            session, uuid.uuid4(), [BasketItemIn(product_id=milk.id, quantity=1)], points_to_spend="all"
        )

        created_data = receipt_service.create_receipt.call_args.args[2]
        assert created_data.points_to_spend == "all"

    def test_points_to_spend_defaults_to_none(
        self,
        service: BasketService,
        repo: MagicMock,
        receipt_repo: MagicMock,
        store_repo: MagicMock,
        discount_calc: MagicMock,
        receipt_service: MagicMock,
        session: MagicMock,
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        store = _make_store()
        receipt_repo.list_by_loyalty_card.return_value = ([], 0)
        store_repo.list_all.return_value = [store]
        discount_calc.calculate.return_value = [
            CalculatedItem(
                product_id=milk.id, product_name=milk.name, quantity=1,
                base_price=Decimal("100.00"), paid_price=Decimal("100.00"),
                discount_id=None, discounted_amount=Decimal("0.00"),
            )
        ]
        receipt_service.create_receipt.return_value = (MagicMock(), True)

        service.checkout(session, uuid.uuid4(), [BasketItemIn(product_id=milk.id, quantity=1)])

        created_data = receipt_service.create_receipt.call_args.args[2]
        assert created_data.points_to_spend is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry -C web run pytest tests/webx5/services/test_basket_assistant.py::TestCheckout::test_points_to_spend_forwarded_to_receipt_create -v`
Expected: FAIL — `TypeError: BasketService.checkout() got an unexpected keyword argument 'points_to_spend'`.

- [ ] **Step 3: Implement**

In `web/src/webx5/schemas/basket.py`, replace:

```python
class CheckoutRequest(BaseModel):
    items: list[BasketItemIn]
```

with:

```python
class CheckoutRequest(BaseModel):
    items: list[BasketItemIn]
    points_to_spend: PointsToSpend = None
```

In `web/src/webx5/services/basket_assistant.py`, replace the `checkout` signature:

```python
    def checkout(
        self,
        session: Session,
        user_id: uuid.UUID,
        items: list[BasketItemIn],
    ) -> ReceiptResponse:
```

with:

```python
    def checkout(
        self,
        session: Session,
        user_id: uuid.UUID,
        items: list[BasketItemIn],
        points_to_spend: PointsToSpend = None,
    ) -> ReceiptResponse:
```

and replace the `ReceiptCreate(...)` construction inside `checkout`:

```python
        data = ReceiptCreate(
            loyalty_card_id=user_id,
            store_id=store.id,
            channel="offline",
            items=receipt_items,
        )
```

with:

```python
        data = ReceiptCreate(
            loyalty_card_id=user_id,
            store_id=store.id,
            channel="offline",
            items=receipt_items,
            points_to_spend=points_to_spend,
        )
```

In `web/src/webx5/routes/basket.py`, replace:

```python
@basket_router.post("/checkout", response_model=ReceiptResponse, status_code=201)
def post_basket_checkout(
    data: CheckoutRequest,
    session: SessionDep,
    user_id: CurrentUserUUID,
) -> ReceiptResponse:
    from webx5.core.basket import basket_service

    return basket_service.checkout(session, user_id, data.items)
```

with:

```python
@basket_router.post("/checkout", response_model=ReceiptResponse, status_code=201)
def post_basket_checkout(
    data: CheckoutRequest,
    session: SessionDep,
    user_id: CurrentUserUUID,
) -> ReceiptResponse:
    from webx5.core.basket import basket_service

    return basket_service.checkout(session, user_id, data.items, data.points_to_spend)
```

Add a route-level test to `web/tests/webx5/routes/test_basket.py`'s `TestPostBasketCheckout` class:

```python
    def test_forwards_points_to_spend(self) -> None:
        from webx5.schemas.receipt import ReceiptResponse

        captured: dict = {}

        def _fake_checkout(self, session, user_id, items, points_to_spend=None):
            captured["points_to_spend"] = points_to_spend
            return ReceiptResponse(
                id=uuid.uuid4(),
                purchase_date="2026-09-05T12:00:00Z",
                store_id=uuid.uuid4(),
                loyalty_card_id=user_id,
                channel="offline",
                items=[],
                total_base=Decimal("0"),
                total_paid=Decimal("0"),
                total_saved=Decimal("0"),
            )

        with patch("webx5.services.basket_assistant.BasketService.checkout", _fake_checkout):
            resp = client.post(
                "/basket/checkout",
                json={"items": [{"product_id": str(uuid.uuid4()), "quantity": 1}], "points_to_spend": "all"},
                headers=_bearer(_token()),
            )
        assert resp.status_code == 201
        assert captured["points_to_spend"] == "all"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry -C web run pytest tests/webx5/services/test_basket_assistant.py tests/webx5/routes/test_basket.py -v`
Expected: PASS.

Then run the full backend suite once: `poetry -C web run pytest`.
Expected: same pre-existing 5 unrelated failures (`test_auth.py`, `test_challenges.py`), everything else passing, no new failures.

- [ ] **Step 5: Commit**

```bash
git add web/src/webx5/schemas/basket.py web/src/webx5/services/basket_assistant.py web/src/webx5/routes/basket.py web/tests/webx5/services/test_basket_assistant.py web/tests/webx5/routes/test_basket.py
git commit -m "feat: support points_to_spend on POST /basket/checkout"
```

---

### Task 3: Frontend hook — preview + points toggle, bottom-tab nav

**Files:**
- Modify: `x5mobile/src/hooks/useBasket.ts`
- Modify: `x5mobile/src/app/index.tsx`

**Interfaces:**
- Consumes: `POST /basket/preview` (Task 1), `POST /basket/checkout` with `points_to_spend` (Task 2).
- Produces: `useBasket(token, onOrderPlaced?) -> {items, loading, message, sendInstruction, checkout, preview, spendPoints, setSpendPoints}` where `preview: BasketPreview | null`, `spendPoints: boolean`. Used by Task 4's `savings-view.tsx`.

No test framework on the frontend — verification is `npx tsc --noEmit` plus the manual curl checks in Step 4 below.

- [ ] **Step 1: Add preview types and state to `useBasket.ts`**

Replace the full content of `x5mobile/src/hooks/useBasket.ts`:

```typescript
import { useEffect, useState } from 'react';

import { apiFetch } from '@/api/client';

export interface BasketItem {
  product_id: string;
  name: string;
  quantity: number;
  price: number;
}

interface SuggestedBasketResponse {
  items: BasketItem[];
}

interface AssistantResponse {
  items: BasketItem[];
  applied: boolean;
  message: string | null;
}

interface CheckoutResponse {
  total_saved: number;
}

export interface BasketPreviewItem {
  product_id: string;
  product_name: string;
  quantity: number;
  base_price: number;
  paid_price: number;
  discount_id: string | null;
  discounted_amount: number;
}

export interface BasketPreviewCashback {
  points_available: number;
  points_to_apply: number;
  cashback_rub: number;
  total_paid_rub: number;
  points_balance_after: number;
  points_capped_by: 'none' | 'balance' | 'receipt_total';
  rate_points_per_rub: number;
}

export interface BasketPreview {
  items: BasketPreviewItem[];
  total_base: number;
  total_paid: number;
  total_saved: number;
  cashback: BasketPreviewCashback | null;
}

export function useBasket(token: string | null, onOrderPlaced?: () => void) {
  const [items, setItems] = useState<BasketItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<BasketPreview | null>(null);
  const [spendPoints, setSpendPoints] = useState(false);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    apiFetch<SuggestedBasketResponse>('/basket/suggested', token)
      .then((data) => setItems(data.items))
      .catch((e: Error) => setMessage(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (!token) return;
    apiFetch<BasketPreview>('/basket/preview', token, {
      method: 'POST',
      body: JSON.stringify({
        items: items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
        points_to_spend: spendPoints ? 'all' : null,
      }),
    })
      .then(setPreview)
      .catch(() => setPreview(null));
  }, [token, items, spendPoints]);

  async function sendInstruction(instruction: string) {
    if (!token || !instruction.trim()) return;
    setLoading(true);
    try {
      const res = await apiFetch<AssistantResponse>('/basket/assistant', token, {
        method: 'POST',
        body: JSON.stringify({
          items: items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
          instruction,
        }),
      });
      setItems(res.items);
      setMessage(res.applied ? null : res.message);
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Ошибка запроса');
    } finally {
      setLoading(false);
    }
  }

  async function checkout() {
    if (!token || items.length === 0) return;
    setLoading(true);
    try {
      const res = await apiFetch<CheckoutResponse>('/basket/checkout', token, {
        method: 'POST',
        body: JSON.stringify({
          items: items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
          points_to_spend: spendPoints ? 'all' : null,
        }),
      });
      setItems([]);
      setPreview(null);
      setSpendPoints(false);
      setMessage(`Заказ оформлен! Сэкономлено ${Math.round(res.total_saved)} ₽`);
      onOrderPlaced?.();
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Ошибка оформления заказа');
    } finally {
      setLoading(false);
    }
  }

  return { items, loading, message, sendInstruction, checkout, preview, spendPoints, setSpendPoints };
}
```

- [ ] **Step 2: Wire the bottom-tab "Корзина" button to the savings screen**

In `x5mobile/src/app/index.tsx`, find:

```typescript
      <CustomTabBar
        activeScreen={screen as TabScreen}
        onTabPress={(tab) => navigate(tab)}
```

replace with:

```typescript
      <CustomTabBar
        activeScreen={screen as TabScreen}
        onTabPress={(tab) => navigate(tab === 'cart' ? 'savings' : tab)}
```

- [ ] **Step 3: Type-check**

Run: `cd x5mobile && npx tsc --noEmit`
Expected: no errors from `useBasket.ts` / `index.tsx`.

- [ ] **Step 4: Manual verification against the running backend**

Rebuild the backend image first if it wasn't already rebuilt after Tasks 1-2 of this plan (`web/src/webx5` is baked into the Docker image, not volume-mounted):

```bash
cd /Users/dimonzhi/Documents/proga/x5hack
docker compose build web worker beat && docker compose up -d web worker beat
```

Then:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/login -H "Content-Type: application/json" -d '{"phone":"+79006472484"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

SUGGESTED=$(curl -s http://localhost:8000/basket/suggested -H "Authorization: Bearer $TOKEN")
ITEMS=$(echo "$SUGGESTED" | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; print(json.dumps([{'product_id': i['product_id'], 'quantity': i['quantity']} for i in items]))")

curl -s -w "\nHTTP:%{http_code}\n" -X POST http://localhost:8000/basket/preview \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"items\": $ITEMS}"
# Expected: HTTP:200, JSON with per-item base_price/paid_price and a `cashback` block
# (or null cashback only if points_available happens to be 0 for this demo user)

curl -s -w "\nHTTP:%{http_code}\n" -X POST http://localhost:8000/basket/preview \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"items": []}'
# Expected: HTTP:200 (NOT 422), items: [], all totals 0
```

- [ ] **Step 5: Commit**

```bash
git add x5mobile/src/hooks/useBasket.ts x5mobile/src/app/index.tsx
git commit -m "feat: add price/points preview to useBasket, wire cart tab to savings screen"
```

---

### Task 4: UI — price, discount, points toggle

**Files:**
- Modify: `x5mobile/src/components/screens/savings-view.tsx`

**Interfaces:**
- Consumes: `useBasket(token, onOrderPlaced)` returning `{..., preview, spendPoints, setSpendPoints}` (Task 3).

No test framework — verification is `npx tsc --noEmit` plus the manual walkthrough in Step 4.

- [ ] **Step 1: Destructure the new hook fields and import `Switch`**

In `x5mobile/src/components/screens/savings-view.tsx`, replace the import line:

```typescript
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
```

with:

```typescript
import { ActivityIndicator, ScrollView, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';
```

Replace:

```typescript
  const { items: basketItems, loading: basketLoading, message: basketMessage, sendInstruction, checkout } = useBasket(token, onOrderPlaced);
```

with:

```typescript
  const {
    items: basketItems,
    loading: basketLoading,
    message: basketMessage,
    sendInstruction,
    checkout,
    preview,
    spendPoints,
    setSpendPoints,
  } = useBasket(token, onOrderPlaced);
```

- [ ] **Step 2: Show base/discounted price per item**

Replace the item-rendering block:

```typescript
          ) : basketItems.length > 0 ? (
            basketItems.map((item: BasketItem) => (
              <View key={item.product_id} style={styles.basketRow}>
                <Text style={styles.basketItemName}>{item.name}</Text>
                <Text style={styles.basketItemQty}>{item.quantity} шт</Text>
              </View>
            ))
          ) : !basketMessage?.startsWith('Заказ оформлен') ? (
```

with:

```typescript
          ) : basketItems.length > 0 ? (
            basketItems.map((item: BasketItem) => {
              const previewItem = preview?.items.find((p) => p.product_id === item.product_id);
              const unitPaid = previewItem?.paid_price ?? item.price;
              const unitBase = previewItem?.base_price ?? item.price;
              const hasDiscount = unitPaid < unitBase;
              return (
                <View key={item.product_id} style={styles.basketRow}>
                  <View style={styles.basketItemInfo}>
                    <Text style={styles.basketItemName}>{item.name}</Text>
                    <Text style={styles.basketItemQty}>{item.quantity} шт</Text>
                  </View>
                  <View style={styles.basketItemPrices}>
                    {hasDiscount && (
                      <Text style={styles.basketItemBasePrice}>{Math.round(unitBase * item.quantity)} ₽</Text>
                    )}
                    <Text style={styles.basketItemPaidPrice}>{Math.round(unitPaid * item.quantity)} ₽</Text>
                  </View>
                </View>
              );
            })
          ) : !basketMessage?.startsWith('Заказ оформлен') ? (
```

- [ ] **Step 3: Add the totals + points-toggle block**

Find:

```typescript
          {basketMessage && <Text style={styles.basketMessage}>{basketMessage}</Text>}
          <Text style={styles.appiLabel}>🍊 Спроси Аппи</Text>
```

replace with:

```typescript
          {preview && basketItems.length > 0 && (
            <View style={styles.basketTotals}>
              <View style={styles.basketTotalsRow}>
                <Text style={styles.basketTotalsLabel}>Итого</Text>
                <Text style={styles.basketTotalsValue}>{Math.round(preview.total_paid)} ₽</Text>
              </View>
              {preview.total_base > preview.total_paid && (
                <View style={styles.basketTotalsRow}>
                  <Text style={styles.basketTotalsLabel}>Скидка</Text>
                  <Text style={styles.basketTotalsDiscount}>
                    −{Math.round(preview.total_base - preview.total_paid)} ₽
                  </Text>
                </View>
              )}
              {preview.cashback && preview.cashback.points_available > 0 && (
                <View style={styles.basketTotalsRow}>
                  <Text style={styles.basketTotalsLabel}>
                    Списать баллы ({preview.cashback.points_available})
                  </Text>
                  <Switch
                    value={spendPoints}
                    onValueChange={setSpendPoints}
                    trackColor={{ false: BrandColors.cardBorder, true: BrandColors.green }}
                  />
                </View>
              )}
              {spendPoints && preview.cashback && preview.cashback.cashback_rub > 0 && (
                <View style={styles.basketTotalsRow}>
                  <Text style={styles.basketTotalsLabel}>Итого с баллами</Text>
                  <Text style={styles.basketTotalsValueGreen}>
                    {Math.round(preview.cashback.total_paid_rub)} ₽
                  </Text>
                </View>
              )}
            </View>
          )}
          {basketMessage && <Text style={styles.basketMessage}>{basketMessage}</Text>}
          <Text style={styles.appiLabel}>🍊 Спроси Аппи</Text>
```

- [ ] **Step 4: Add the new styles**

Find:

```typescript
  basketItemName: {
    fontSize: 14,
    color: BrandColors.textPrimary,
  },
  basketItemQty: {
    fontSize: 13,
    color: BrandColors.textSecondary,
    fontWeight: '600',
  },
```

replace with:

```typescript
  basketItemInfo: {
    flex: 1,
  },
  basketItemName: {
    fontSize: 14,
    color: BrandColors.textPrimary,
  },
  basketItemQty: {
    fontSize: 13,
    color: BrandColors.textSecondary,
    fontWeight: '600',
  },
  basketItemPrices: {
    alignItems: 'flex-end',
  },
  basketItemBasePrice: {
    fontSize: 12,
    color: BrandColors.textSecondary,
    textDecorationLine: 'line-through',
  },
  basketItemPaidPrice: {
    fontSize: 14,
    fontWeight: '700',
    color: BrandColors.textPrimary,
  },
  basketTotals: {
    borderTopWidth: 1,
    borderTopColor: BrandColors.cardBorder,
    paddingTop: 10,
    gap: 6,
  },
  basketTotalsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  basketTotalsLabel: {
    fontSize: 13,
    color: BrandColors.textSecondary,
  },
  basketTotalsValue: {
    fontSize: 15,
    fontWeight: '700',
    color: BrandColors.textPrimary,
  },
  basketTotalsValueGreen: {
    fontSize: 15,
    fontWeight: '700',
    color: BrandColors.green,
  },
  basketTotalsDiscount: {
    fontSize: 13,
    fontWeight: '600',
    color: BrandColors.green,
  },
```

- [ ] **Step 5: Type-check**

Run: `cd x5mobile && npx tsc --noEmit`
Expected: no errors from `savings-view.tsx`.

- [ ] **Step 6: Manual verification in the running app**

With the Docker stack up (rebuilt per Task 3's Step 4) and Expo web running on `http://localhost:8081` (start it if not already running: `cd x5mobile && npx expo start --web`):

1. Log in with a demo phone with purchase history (e.g. `+79006472484`).
2. From the home screen, tap the bottom-bar "Корзина" tab — it should open the "Экономия" screen (same screen the existing "Корзина на неделю" card lives on), not a blank screen.
3. In the basket card, confirm each item shows a price; if a discount applies to a product, confirm the original price appears struck through next to the discounted price.
4. Confirm a totals block appears below the item list ("Итого", and "Скидка" if any item has a discount).
5. If the demo user has a points balance, confirm the "Списать баллы (N)" toggle appears; flip it and confirm the totals update to show "Итого с баллами" with a lower amount (poll — the preview re-fetches on toggle, may take a second).
6. Tap "Оформить заказ" with the toggle on; confirm the checkout succeeds and the success message still shows correctly (this exercises the points-spend path end-to-end).

- [ ] **Step 7: Commit**

```bash
git add x5mobile/src/components/screens/savings-view.tsx
git commit -m "feat: show price/discount per item and points-spend toggle in weekly basket"
```
