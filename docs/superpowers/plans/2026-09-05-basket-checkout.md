# Оформление заказа из корзины на неделю — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Кнопка «Оформить заказ» в корзине на неделю создаёт реальный `Receipt` (со скидками, как у кассового терминала) и обновляет карточку экономии.

**Architecture:** Новый `BasketService.checkout()` оркеструет уже существующие `DiscountCalculatorService.calculate()` и `ReceiptService.create_receipt()` — никакой новой персистентности, никакого дублирования бизнес-логики. Магазин для чека берётся из последнего чека пользователя, с fallback на первый магазин в БД. Фронт: новый метод в `useBasket.ts`, `refetch` в `useEconomy.ts`, кнопка в `savings-view.tsx`.

**Tech Stack:** FastAPI + SQLAlchemy (sync), Pydantic v2 (бэкенд `web/src/webx5`); Expo/React Native/TypeScript (фронт `x5mobile/`).

**Spec:** [docs/superpowers/specs/2026-09-05-basket-checkout-design.md](../specs/2026-09-05-basket-checkout-design.md)

## Global Constraints

- RSI-слои: routes = schema + session → service; вся бизнес-логика в services; никакого SQL в routes.
- DI: сервис получает зависимости через конструктор, не создаёт их сам (`.claude/rules/scripts-and-services.md`).
- Новых таблиц/миграций в этой фиче нет — корзина остаётся стейтлес.
- Существующий терминальный `POST /receipts` не трогаем (не входит в объём).
- Новый эндпоинт — `CurrentUserUUID` auth (как `/basket/suggested`, `/basket/assistant`), НЕ `TerminalTokenDep`.
- `channel="offline"`, `points_to_spend` не используется (вне объёма, см. BACKLOG.md).
- Тесты бэкенда: `pytest` в `web/tests/webx5/...`, зеркалирует `src/webx5/...`.
- У фронта (`x5mobile/`) нет тестового фреймворка — верификация фронтенд-задач ручная (curl + запуск в браузере/симуляторе).

---

### Task 1: `ReceiptService.build_receipt_response()`

**Files:**
- Modify: `web/src/webx5/services/receipt.py`
- Test: `web/tests/webx5/services/test_receipt_service.py`

**Interfaces:**
- Consumes: `ReceiptRepository.get_items_with_products(session, receipt_id) -> list[tuple[ReceiptItem, Product]]` (уже существует, `web/src/webx5/crud/receipt.py:136`).
- Produces: `ReceiptService.build_receipt_response(session: Session, receipt: Receipt) -> ReceiptResponse` — используется Task 2's `BasketService.checkout()`.

Логика извлекается из `web/src/webx5/routes/receipts.py:140-184` (существующий терминальный `create_receipt` route) один в один — не меняется, только переносится на слой Service, чтобы второй вызывающий код (Task 3) её не дублировал.

- [ ] **Step 1: Write the failing test**

Добавь в конец `web/tests/webx5/services/test_receipt_service.py` (использует уже существующие в файле `_make_product`, `_make_store`, `_make_receipt`, фикстуры `receipt_repo`/`discount_repo`/`service`/`session`):

```python
from webx5.entities.receipt import ReceiptItem
from webx5.schemas.receipt import ReceiptResponse


def _make_receipt_item(*, product_id: uuid.UUID, receipt_id: uuid.UUID) -> ReceiptItem:
    ri = ReceiptItem()
    ri.id = uuid.uuid4()
    ri.receipt_id = receipt_id
    ri.product_id = product_id
    ri.quantity = 2
    ri.base_price_at_purchase = Decimal("100.00")
    ri.paid_price = Decimal("90.00")
    ri.discounted_amount = Decimal("10.00")
    ri.discount_id = None
    return ri


class TestBuildReceiptResponse:
    def test_builds_response_with_totals(
        self, service: ReceiptService, receipt_repo: MagicMock, session: MagicMock
    ) -> None:
        product = _make_product()
        receipt = _make_receipt()
        receipt.cashback_applied_points = 0
        receipt.cashback_applied_rub = 0
        receipt.points_rate_at_purchase = None
        item = _make_receipt_item(product_id=product.id, receipt_id=receipt.id)
        receipt_repo.get_items_with_products.return_value = [(item, product)]

        result = service.build_receipt_response(session, receipt)

        assert isinstance(result, ReceiptResponse)
        assert result.id == receipt.id
        assert result.store_id == receipt.store_id
        assert len(result.items) == 1
        assert result.items[0].product_id == product.id
        assert result.total_base == Decimal("200.00")
        assert result.total_paid == Decimal("180.00")
        assert result.discount_saved_rub == Decimal("20.00")
        assert result.total_saved == Decimal("20.00")

    def test_subtracts_cashback_from_total_paid(
        self, service: ReceiptService, receipt_repo: MagicMock, session: MagicMock
    ) -> None:
        product = _make_product()
        receipt = _make_receipt()
        receipt.cashback_applied_points = 500
        receipt.cashback_applied_rub = 50
        receipt.points_rate_at_purchase = 10
        item = _make_receipt_item(product_id=product.id, receipt_id=receipt.id)
        item.discounted_amount = Decimal("0.00")
        item.paid_price = Decimal("100.00")
        receipt_repo.get_items_with_products.return_value = [(item, product)]

        result = service.build_receipt_response(session, receipt)

        assert result.total_paid == Decimal("150.00")  # 200 base paid - 50 cashback
        assert result.total_saved == Decimal("50.00")  # 0 discount + 50 cashback
        assert result.cashback_applied_rub == 50
        assert result.points_rate_at_purchase == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry -C web run pytest tests/webx5/services/test_receipt_service.py::TestBuildReceiptResponse -v`
Expected: FAIL with `AttributeError: 'ReceiptService' object has no attribute 'build_receipt_response'`

- [ ] **Step 3: Implement `build_receipt_response`**

В `web/src/webx5/services/receipt.py` замени строку импорта схем:

```python
from webx5.schemas.receipt import ReceiptCreate
```

на:

```python
from webx5.schemas.receipt import ReceiptCreate, ReceiptItemResponse, ReceiptResponse
```

Добавь новый метод в класс `ReceiptService` (после `create_receipt`, тот же уровень отступа):

```python
    def build_receipt_response(self, session: Session, receipt: Receipt) -> ReceiptResponse:
        items_with_products = self.receipt_repo.get_items_with_products(session, receipt.id)

        item_responses = [
            ReceiptItemResponse(
                id=ri.id,
                product_id=ri.product_id,
                quantity=ri.quantity,
                base_price_at_purchase=Decimal(str(ri.base_price_at_purchase)),
                paid_price=Decimal(str(ri.paid_price)),
                discounted_amount=Decimal(str(ri.discounted_amount)),
                discount_id=ri.discount_id,
            )
            for ri, _product in items_with_products
        ]

        total_base = sum(i.base_price_at_purchase * i.quantity for i in item_responses)
        total_paid_before_cashback = sum(i.paid_price * i.quantity for i in item_responses)
        cashback_rub = Decimal(str(receipt.cashback_applied_rub))
        discount_saved = total_base - total_paid_before_cashback
        total_paid = max(total_paid_before_cashback - cashback_rub, Decimal("0"))

        return ReceiptResponse(
            id=receipt.id,
            purchase_date=receipt.purchase_date,
            store_id=receipt.store_id,
            loyalty_card_id=receipt.loyalty_card_id,
            channel=receipt.channel,
            items=item_responses,
            total_base=total_base,
            total_paid=total_paid,
            total_saved=discount_saved + cashback_rub,
            discount_saved_rub=discount_saved,
            cashback_applied_points=int(receipt.cashback_applied_points),
            cashback_applied_rub=int(receipt.cashback_applied_rub),
            points_rate_at_purchase=(
                int(receipt.points_rate_at_purchase)
                if receipt.points_rate_at_purchase is not None
                else None
            ),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry -C web run pytest tests/webx5/services/test_receipt_service.py -v`
Expected: PASS, все тесты в файле (включая уже существующие) зелёные.

- [ ] **Step 5: Commit**

```bash
git add web/src/webx5/services/receipt.py web/tests/webx5/services/test_receipt_service.py
git commit -m "feat: extract ReceiptService.build_receipt_response for reuse by basket checkout"
```

---

### Task 2: `BasketService.checkout()`

**Files:**
- Modify: `web/src/webx5/services/basket_assistant.py`
- Modify: `web/src/webx5/core/basket.py`
- Test: `web/tests/webx5/services/test_basket_assistant.py`

**Interfaces:**
- Consumes: `ReceiptService.build_receipt_response(session, receipt) -> ReceiptResponse` (Task 1). `DiscountCalculatorService.calculate(items: list[CartItem], store: Store, loyalty_card_id: uuid.UUID | None, session: Session) -> list[CalculatedItem]` (уже существует, `web/src/webx5/services/discount_calculator.py:54`). `ReceiptRepository.list_by_loyalty_card(session, loyalty_card_id, page=1, size=1) -> tuple[list[Receipt], int]` (уже существует, `web/src/webx5/crud/receipt.py:79`). `StoreRepository.list_all(session) -> list[Store]` и `.get_by_id(session, store_id) -> Store | None` (уже существуют, `web/src/webx5/crud/store.py`). `ReceiptService.create_receipt(session, receipt_id: uuid.UUID, data: ReceiptCreate) -> tuple[Receipt, bool]` (уже существует).
- Produces: `BasketService.checkout(session: Session, user_id: uuid.UUID, items: list[BasketItemIn]) -> ReceiptResponse` — используется Task 3's route. Raises `fastapi.HTTPException(422)` на пустую корзину, неизвестный `product_id`, или отсутствие магазинов в БД.

- [ ] **Step 1: Write the failing test**

Замени фикстуры в начале `web/tests/webx5/services/test_basket_assistant.py`. Текущий блок:

```python
@pytest.fixture()
def repo() -> MagicMock:
    return MagicMock(spec=BasketRepository)


@pytest.fixture()
def service(repo: MagicMock) -> BasketService:
    return BasketService(repo=repo, model="fake/model")


@pytest.fixture()
def session() -> MagicMock:
    return MagicMock()
```

замени на:

```python
@pytest.fixture()
def repo() -> MagicMock:
    return MagicMock(spec=BasketRepository)


@pytest.fixture()
def receipt_repo() -> MagicMock:
    return MagicMock(spec=ReceiptRepository)


@pytest.fixture()
def store_repo() -> MagicMock:
    return MagicMock(spec=StoreRepository)


@pytest.fixture()
def discount_calc() -> MagicMock:
    return MagicMock(spec=DiscountCalculatorService)


@pytest.fixture()
def receipt_service() -> MagicMock:
    return MagicMock(spec=ReceiptService)


@pytest.fixture()
def service(
    repo: MagicMock,
    receipt_repo: MagicMock,
    store_repo: MagicMock,
    discount_calc: MagicMock,
    receipt_service: MagicMock,
) -> BasketService:
    return BasketService(
        repo=repo,
        receipt_repo=receipt_repo,
        store_repo=store_repo,
        discount_calc=discount_calc,
        receipt_service=receipt_service,
        model="fake/model",
    )


@pytest.fixture()
def session() -> MagicMock:
    return MagicMock()
```

Добавь новые импорты в начало файла (после существующего `from webx5.services.basket_assistant import BasketService`):

```python
from fastapi import HTTPException

from webx5.crud.receipt import ReceiptRepository
from webx5.crud.store import StoreRepository
from webx5.entities.store import Store
from webx5.services.discount_calculator import CalculatedItem, DiscountCalculatorService
from webx5.services.receipt import ReceiptService
```

Добавь `_make_store` рядом с `_make_product`:

```python
def _make_store() -> Store:
    s = Store()
    s.id = uuid.uuid4()
    s.format_id = uuid.uuid4()
    s.geo_cluster = "d_01"
    return s
```

Добавь в конец файла новый класс тестов:

```python
class TestCheckout:
    def test_applies_discount_and_uses_last_receipt_store(
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

        discount_id = uuid.uuid4()
        discount_calc.calculate.return_value = [
            CalculatedItem(
                product_id=milk.id,
                product_name=milk.name,
                quantity=2,
                base_price=Decimal("100.00"),
                paid_price=Decimal("90.00"),
                discount_id=discount_id,
                discounted_amount=Decimal("10.00"),
            )
        ]

        fake_receipt = MagicMock()
        receipt_service.create_receipt.return_value = (fake_receipt, True)
        expected_response = MagicMock()
        receipt_service.build_receipt_response.return_value = expected_response

        user_id = uuid.uuid4()
        result = service.checkout(session, user_id, [BasketItemIn(product_id=milk.id, quantity=2)])

        assert result is expected_response
        store_repo.get_by_id.assert_called_once_with(session, store.id)
        receipt_service.create_receipt.assert_called_once()
        call_args = receipt_service.create_receipt.call_args.args
        assert call_args[0] is session
        created_data = call_args[2]
        assert created_data.store_id == store.id
        assert created_data.loyalty_card_id == user_id
        assert created_data.channel == "offline"
        assert created_data.items[0].discount_id == discount_id
        assert created_data.items[0].quantity == 2
        receipt_service.build_receipt_response.assert_called_once_with(session, fake_receipt)

    def test_falls_back_to_first_store_when_no_receipt_history(
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
        receipt_repo.list_by_loyalty_card.return_value = ([], 0)
        store = _make_store()
        store_repo.list_all.return_value = [store]
        discount_calc.calculate.return_value = [
            CalculatedItem(
                product_id=milk.id,
                product_name=milk.name,
                quantity=1,
                base_price=Decimal("50.00"),
                paid_price=Decimal("50.00"),
                discount_id=None,
                discounted_amount=Decimal("0.00"),
            )
        ]
        receipt_service.create_receipt.return_value = (MagicMock(), True)

        service.checkout(session, uuid.uuid4(), [BasketItemIn(product_id=milk.id, quantity=1)])

        store_repo.list_all.assert_called_once_with(session)
        created_data = receipt_service.create_receipt.call_args.args[2]
        assert created_data.store_id == store.id

    def test_empty_basket_raises_422(self, service: BasketService, session: MagicMock) -> None:
        with pytest.raises(HTTPException) as exc_info:
            service.checkout(session, uuid.uuid4(), [])
        assert exc_info.value.status_code == 422

    def test_unknown_product_id_raises_422(
        self, service: BasketService, repo: MagicMock, session: MagicMock
    ) -> None:
        repo.get_full_catalog.return_value = []
        with pytest.raises(HTTPException) as exc_info:
            service.checkout(session, uuid.uuid4(), [BasketItemIn(product_id=uuid.uuid4(), quantity=1)])
        assert exc_info.value.status_code == 422

    def test_no_stores_available_raises_422(
        self,
        service: BasketService,
        repo: MagicMock,
        receipt_repo: MagicMock,
        store_repo: MagicMock,
        session: MagicMock,
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        receipt_repo.list_by_loyalty_card.return_value = ([], 0)
        store_repo.list_all.return_value = []

        with pytest.raises(HTTPException) as exc_info:
            service.checkout(session, uuid.uuid4(), [BasketItemIn(product_id=milk.id, quantity=1)])
        assert exc_info.value.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry -C web run pytest tests/webx5/services/test_basket_assistant.py -v`
Expected: FAIL — `TypeError: BasketService.__init__() got an unexpected keyword argument 'receipt_repo'` (текущий конструктор принимает только `repo` и `model`).

- [ ] **Step 3: Implement `checkout`**

В `web/src/webx5/services/basket_assistant.py` замени блок импортов в начале файла:

```python
from __future__ import annotations

import uuid
from decimal import Decimal

import structlog
from sqlalchemy.orm import Session

from webx5.core.llm import call_openrouter_tools
from webx5.crud.basket import BasketRepository
from webx5.entities.product import Product
from webx5.schemas.basket import AssistantResponse, BasketItem, BasketItemIn
```

на:

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

Добавь константы рядом с `CANNOT_UNDERSTAND_MESSAGE`/`LLM_FAILURE_MESSAGE`:

```python
CHECKOUT_EMPTY_BASKET_MESSAGE = "Корзина пуста"
CHECKOUT_NO_STORES_MESSAGE = "Не найдено ни одного магазина"
```

Замени `__init__` класса `BasketService`:

```python
    def __init__(self, repo: BasketRepository, model: str = "deepseek/deepseek-chat") -> None:
        self.repo = repo
        self.model = model
```

на:

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

Добавь новый метод `checkout` в класс `BasketService`, сразу после `apply_instruction` (перед `_build_system_prompt`):

```python
    def checkout(
        self,
        session: Session,
        user_id: uuid.UUID,
        items: list[BasketItemIn],
    ) -> ReceiptResponse:
        if not items:
            raise HTTPException(status_code=422, detail=CHECKOUT_EMPTY_BASKET_MESSAGE)

        catalog = self.repo.get_full_catalog(session)
        catalog_by_id = {p.id: p for p in catalog}
        missing = [str(i.product_id) for i in items if i.product_id not in catalog_by_id]
        if missing:
            raise HTTPException(
                status_code=422,
                detail={"detail": "Unknown product_ids", "unknown_product_ids": missing},
            )

        receipts, _total = self.receipt_repo.list_by_loyalty_card(session, user_id, page=1, size=1)
        if receipts:
            store = self.store_repo.get_by_id(session, receipts[0].store_id)
        else:
            stores = self.store_repo.list_all(session)
            if not stores:
                raise HTTPException(status_code=422, detail=CHECKOUT_NO_STORES_MESSAGE)
            store = stores[0]

        cart_items = [CartItem(product_id=i.product_id, quantity=i.quantity) for i in items]
        calculated = self.discount_calc.calculate(
            items=cart_items, store=store, loyalty_card_id=user_id, session=session
        )
        receipt_items = [
            ReceiptItemCreate(product_id=c.product_id, quantity=c.quantity, discount_id=c.discount_id)
            for c in calculated
        ]
        data = ReceiptCreate(
            loyalty_card_id=user_id,
            store_id=store.id,
            channel="offline",
            items=receipt_items,
        )
        receipt, _is_new = self.receipt_service.create_receipt(session, uuid.uuid4(), data)
        return self.receipt_service.build_receipt_response(session, receipt)
```

Теперь обнови wiring в `web/src/webx5/core/basket.py`. Текущее содержимое:

```python
import os

from webx5.crud.basket import BasketRepository
from webx5.services.basket_assistant import BasketService

BASKET_LLM_MODEL = os.environ.get("BASKET_LLM_MODEL", "anthropic/claude-haiku-4.5")

basket_repo = BasketRepository()
basket_service = BasketService(repo=basket_repo, model=BASKET_LLM_MODEL)
```

замени на:

```python
import os

from webx5.core.purchases import discount_calculator_service, receipt_service
from webx5.crud.basket import BasketRepository
from webx5.crud.receipt import ReceiptRepository
from webx5.crud.store import StoreRepository
from webx5.services.basket_assistant import BasketService

BASKET_LLM_MODEL = os.environ.get("BASKET_LLM_MODEL", "anthropic/claude-haiku-4.5")

basket_repo = BasketRepository()
basket_service = BasketService(
    repo=basket_repo,
    receipt_repo=ReceiptRepository(),
    store_repo=StoreRepository(),
    discount_calc=discount_calculator_service,
    receipt_service=receipt_service,
    model=BASKET_LLM_MODEL,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry -C web run pytest tests/webx5/services/test_basket_assistant.py -v`
Expected: PASS, все тесты в файле (старые + новые) зелёные.

- [ ] **Step 5: Commit**

```bash
git add web/src/webx5/services/basket_assistant.py web/src/webx5/core/basket.py web/tests/webx5/services/test_basket_assistant.py
git commit -m "feat: add BasketService.checkout orchestrating discount calc + receipt creation"
```

---

### Task 3: `POST /basket/checkout` route

**Files:**
- Modify: `web/src/webx5/schemas/basket.py`
- Modify: `web/src/webx5/routes/basket.py`
- Test: `web/tests/webx5/routes/test_basket.py`

**Interfaces:**
- Consumes: `BasketService.checkout(session, user_id, items) -> ReceiptResponse` (Task 2).
- Produces: `POST /basket/checkout` — used by Task 4's `useBasket.ts`.

- [ ] **Step 1: Write the failing test**

Добавь в `web/src/webx5/schemas/basket.py`, после класса `AssistantRequest`:

```python
class CheckoutRequest(BaseModel):
    items: list[BasketItemIn]
```

Добавь в конец `web/tests/webx5/routes/test_basket.py`:

```python
class TestPostBasketCheckout:
    def test_returns_created_receipt(self) -> None:
        from webx5.schemas.receipt import ReceiptItemResponse, ReceiptResponse

        fake_response = ReceiptResponse(
            id=uuid.uuid4(),
            purchase_date="2026-09-05T12:00:00Z",
            store_id=uuid.uuid4(),
            loyalty_card_id=uuid.uuid4(),
            channel="offline",
            items=[
                ReceiptItemResponse(
                    id=uuid.uuid4(),
                    product_id=uuid.uuid4(),
                    quantity=2,
                    base_price_at_purchase=Decimal("100.00"),
                    paid_price=Decimal("90.00"),
                    discounted_amount=Decimal("10.00"),
                    discount_id=None,
                )
            ],
            total_base=Decimal("200.00"),
            total_paid=Decimal("180.00"),
            total_saved=Decimal("20.00"),
            discount_saved_rub=Decimal("20.00"),
        )
        with patch(
            "webx5.services.basket_assistant.BasketService.checkout",
            return_value=fake_response,
        ):
            resp = client.post(
                "/basket/checkout",
                json={"items": [{"product_id": str(uuid.uuid4()), "quantity": 2}]},
                headers=_bearer(_token()),
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["total_saved"] == "20.00"
        assert len(body["items"]) == 1

    def test_requires_auth(self) -> None:
        resp = client.post("/basket/checkout", json={"items": []})
        assert resp.status_code == 401

    def test_propagates_service_422(self) -> None:
        from fastapi import HTTPException

        with patch(
            "webx5.services.basket_assistant.BasketService.checkout",
            side_effect=HTTPException(status_code=422, detail="Корзина пуста"),
        ):
            resp = client.post(
                "/basket/checkout",
                json={"items": []},
                headers=_bearer(_token()),
            )
        assert resp.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry -C web run pytest tests/webx5/routes/test_basket.py::TestPostBasketCheckout -v`
Expected: FAIL with `404 Not Found` (маршрут ещё не существует).

- [ ] **Step 3: Implement the route**

Замени `web/src/webx5/routes/basket.py` целиком:

```python
from __future__ import annotations

from fastapi import APIRouter

from webx5.dependencies.auth import CurrentUserUUID
from webx5.dependencies.db import SessionDep
from webx5.schemas.basket import (
    AssistantRequest,
    AssistantResponse,
    CheckoutRequest,
    SuggestedBasketResponse,
)
from webx5.schemas.receipt import ReceiptResponse

basket_router = APIRouter(prefix="/basket", tags=["Basket"])


@basket_router.get("/suggested", response_model=SuggestedBasketResponse)
def get_suggested_basket(session: SessionDep, user_id: CurrentUserUUID) -> SuggestedBasketResponse:
    from webx5.core.basket import basket_service

    items = basket_service.suggest(session, user_id)
    return SuggestedBasketResponse(items=items)


@basket_router.post("/assistant", response_model=AssistantResponse)
def post_basket_assistant(
    data: AssistantRequest,
    session: SessionDep,
    _user_id: CurrentUserUUID,
) -> AssistantResponse:
    from webx5.core.basket import basket_service

    return basket_service.apply_instruction(session, items=data.items, instruction=data.instruction)


@basket_router.post("/checkout", response_model=ReceiptResponse, status_code=201)
def post_basket_checkout(
    data: CheckoutRequest,
    session: SessionDep,
    user_id: CurrentUserUUID,
) -> ReceiptResponse:
    from webx5.core.basket import basket_service

    return basket_service.checkout(session, user_id, data.items)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry -C web run pytest tests/webx5/routes/test_basket.py -v`
Expected: PASS, все тесты в файле зелёные.

Затем прогони полный набор тестов бэкенда, чтобы убедиться, что ничего не сломано:

Run: `poetry -C web run pytest`
Expected: PASS, 0 failures.

- [ ] **Step 5: Commit**

```bash
git add web/src/webx5/schemas/basket.py web/src/webx5/routes/basket.py web/tests/webx5/routes/test_basket.py
git commit -m "feat: add POST /basket/checkout route"
```

---

### Task 4: Frontend hooks — `useBasket.checkout()` + `useEconomy.refetch()`

**Files:**
- Modify: `x5mobile/src/hooks/useBasket.ts`
- Modify: `x5mobile/src/hooks/useEconomy.ts`

**Interfaces:**
- Consumes: `POST /basket/checkout` (Task 3), response shape `{items, total_base, total_paid, total_saved, ...}` (полная `ReceiptResponse`, хуку нужны только `total_saved`).
- Produces: `useBasket(token, onOrderPlaced?) -> {items, loading, message, sendInstruction, checkout}` где `checkout: () => Promise<void>`. `useEconomy(token) -> {economy, loading, error, refetch}` где `refetch: () => void`. Оба используются Task 5's `savings-view.tsx`/`index.tsx`.

Тестового фреймворка на фронте нет (проверено — `package.json` без `test` script, в репозитории нет `*.test.ts*`). Верификация — Step 4 ниже (ручная, через curl к живому бэкенду) и полная ручная проверка в Task 5.

- [ ] **Step 1: Update `useEconomy.ts` to expose `refetch`**

Замени содержимое `x5mobile/src/hooks/useEconomy.ts` целиком:

```typescript
import { useCallback, useEffect, useState } from 'react';

import { apiFetch } from '@/api/client';

export interface EconomySummary {
  total_saved: number;
  total_paid: number;
  receipts_count: number;
}

export function useEconomy(token: string | null) {
  const [economy, setEconomy] = useState<EconomySummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    apiFetch<EconomySummary>('/receipts/economy', token)
      .then(setEconomy)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { economy, loading, error, refetch };
}
```

- [ ] **Step 2: Add `checkout` to `useBasket.ts`**

Замени содержимое `x5mobile/src/hooks/useBasket.ts` целиком:

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

export function useBasket(token: string | null, onOrderPlaced?: () => void) {
  const [items, setItems] = useState<BasketItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    apiFetch<SuggestedBasketResponse>('/basket/suggested', token)
      .then((data) => setItems(data.items))
      .catch((e: Error) => setMessage(e.message))
      .finally(() => setLoading(false));
  }, [token]);

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
        }),
      });
      setItems([]);
      setMessage(`Заказ оформлен! Сэкономлено ${Math.round(res.total_saved)} ₽`);
      onOrderPlaced?.();
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Ошибка оформления заказа');
    } finally {
      setLoading(false);
    }
  }

  return { items, loading, message, sendInstruction, checkout };
}
```

- [ ] **Step 3: Type-check**

Run: `cd x5mobile && npx tsc --noEmit`
Expected: no errors from `useBasket.ts` / `useEconomy.ts`. (Другие уже существующие ошибки типов в проекте, если есть, не в объёме этой задачи — фиксируй только то, что относится к изменённым файлам.)

- [ ] **Step 4: Manual verification against the running backend**

Со стеком, поднятым через `docker compose up -d` (см. README.md), и залогиненным демо-пользователем (телефон из `demo_logins`, см. вывод `seed_receipts.py`):

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/login -H "Content-Type: application/json" -d '{"phone":"+79006472484"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s -X POST http://localhost:8000/basket/checkout \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"items":[]}'
# Expected: 422, {"detail":"Корзина пуста"}

SUGGESTED=$(curl -s http://localhost:8000/basket/suggested -H "Authorization: Bearer $TOKEN")
echo "$SUGGESTED" | python3 -m json.tool

curl -s -w "\nHTTP:%{http_code}\n" -X POST http://localhost:8000/basket/checkout \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"items\": $(echo "$SUGGESTED" | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; print(json.dumps([{'product_id': i['product_id'], 'quantity': i['quantity']} for i in items]))")}"
# Expected: HTTP:201, receipt JSON with total_saved > 0 if any discount matched

curl -s http://localhost:8000/receipts/economy -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# Expected: receipts_count увеличился на 1 по сравнению с проверкой до checkout
```

Если пересобирали backend-образ в предыдущей сессии — пересобери снова (`docker compose build web worker beat && docker compose up -d web worker beat`), иначе контейнер работает со старым кодом.

- [ ] **Step 5: Commit**

```bash
git add x5mobile/src/hooks/useBasket.ts x5mobile/src/hooks/useEconomy.ts
git commit -m "feat: add basket checkout and economy refetch to frontend hooks"
```

---

### Task 5: UI — кнопка «Оформить заказ»

**Files:**
- Modify: `x5mobile/src/components/screens/savings-view.tsx`
- Modify: `x5mobile/src/app/index.tsx`

**Interfaces:**
- Consumes: `useBasket(token, onOrderPlaced)` (Task 4), `useEconomy(token).refetch` (Task 4).

- [ ] **Step 1: Add `onOrderPlaced` prop and wire `useBasket`**

В `x5mobile/src/components/screens/savings-view.tsx` замени:

```typescript
interface SavingsViewProps {
  tasks: Task[];
  leaderboard: LeaderboardEntry[];
  savings: Savings;
  token: string;
  goHome: () => void;
  goHistory: () => void;
  goChallenges: () => void;
}

export function SavingsView({ tasks, leaderboard, savings, token, goHome, goHistory, goChallenges }: SavingsViewProps) {
  const insets = useSafeAreaInsets();
  const { items: basketItems, loading: basketLoading, message: basketMessage, sendInstruction } = useBasket(token);
  const [instructionText, setInstructionText] = useState('');

  function handleSendInstruction() {
    const text = instructionText.trim();
    if (!text) return;
    sendInstruction(text);
    setInstructionText('');
  }
```

на:

```typescript
interface SavingsViewProps {
  tasks: Task[];
  leaderboard: LeaderboardEntry[];
  savings: Savings;
  token: string;
  goHome: () => void;
  goHistory: () => void;
  goChallenges: () => void;
  onOrderPlaced: () => void;
}

export function SavingsView({ tasks, leaderboard, savings, token, goHome, goHistory, goChallenges, onOrderPlaced }: SavingsViewProps) {
  const insets = useSafeAreaInsets();
  const { items: basketItems, loading: basketLoading, message: basketMessage, sendInstruction, checkout } = useBasket(token, onOrderPlaced);
  const [instructionText, setInstructionText] = useState('');

  function handleSendInstruction() {
    const text = instructionText.trim();
    if (!text) return;
    sendInstruction(text);
    setInstructionText('');
  }

  function handleCheckout() {
    checkout();
  }
```

- [ ] **Step 2: Add the checkout button**

Найди блок (внутри `basketCard`, после `basketInputRow`):

```typescript
            <TouchableOpacity
              style={styles.basketSendBtn}
              onPress={handleSendInstruction}
              activeOpacity={0.7}
              disabled={basketLoading || !instructionText.trim()}>
              {basketLoading
                ? <ActivityIndicator color="#fff" size="small" />
                : <Text style={styles.basketSendBtnText}>→</Text>
              }
            </TouchableOpacity>
          </View>
        </View>
```

замени на:

```typescript
            <TouchableOpacity
              style={styles.basketSendBtn}
              onPress={handleSendInstruction}
              activeOpacity={0.7}
              disabled={basketLoading || !instructionText.trim()}>
              {basketLoading
                ? <ActivityIndicator color="#fff" size="small" />
                : <Text style={styles.basketSendBtnText}>→</Text>
              }
            </TouchableOpacity>
          </View>
          <TouchableOpacity
            style={[styles.checkoutBtn, (basketLoading || basketItems.length === 0) && styles.checkoutBtnDisabled]}
            onPress={handleCheckout}
            activeOpacity={0.7}
            disabled={basketLoading || basketItems.length === 0}>
            {basketLoading
              ? <ActivityIndicator color="#fff" size="small" />
              : <Text style={styles.checkoutBtnText}>Оформить заказ</Text>
            }
          </TouchableOpacity>
        </View>
```

(Первый `</View>` закрывает `basketInputRow`, второй — новый закрывающий тег для `basketCard`, замещающий прежний последний `</View>` этого блока.)

- [ ] **Step 3: Add styles**

Найди в `StyleSheet.create` блок:

```typescript
  basketSendBtnText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
  },
```

и добавь сразу после него:

```typescript
  checkoutBtn: {
    backgroundColor: BrandColors.green,
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkoutBtnDisabled: {
    backgroundColor: BrandColors.cardBorder,
  },
  checkoutBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '700',
  },
```

- [ ] **Step 4: Wire `onOrderPlaced` in `index.tsx`**

В `x5mobile/src/app/index.tsx` замени:

```typescript
  const data = useMockData();
  const { economy } = useEconomy(token);
```

на:

```typescript
  const data = useMockData();
  const { economy, refetch: refetchEconomy } = useEconomy(token);
```

Замени:

```typescript
        {screen === 'savings' && (
          <SavingsView
            tasks={data.tasks}
            leaderboard={data.leaderboard}
            savings={{ paid: totalPaid, withoutDiscount: totalPaid + totalSaved }}
            token={token}
            goHome={() => navigate('home')}
            goHistory={() => navigate('history')}
            goChallenges={() => navigate('challenges')}
          />
        )}
```

на:

```typescript
        {screen === 'savings' && (
          <SavingsView
            tasks={data.tasks}
            leaderboard={data.leaderboard}
            savings={{ paid: totalPaid, withoutDiscount: totalPaid + totalSaved }}
            token={token}
            goHome={() => navigate('home')}
            goHistory={() => navigate('history')}
            goChallenges={() => navigate('challenges')}
            onOrderPlaced={refetchEconomy}
          />
        )}
```

- [ ] **Step 5: Type-check**

Run: `cd x5mobile && npx tsc --noEmit`
Expected: no errors from `savings-view.tsx` / `index.tsx`.

- [ ] **Step 6: Manual verification in the running app**

Со стеком в Docker и Expo web (`npx expo start --web`, см. предыдущую переписку этой сессии — уже запущен на `http://localhost:8081` в фоне; если не запущен, поднять заново):

1. Открыть http://localhost:8081, залогиниться демо-номером с историей покупок.
2. Перейти в «Корзина на неделю» (кнопка на главном экране).
3. Убедиться, что корзина не пуста (если пуста — попросить Аппи что-то добавить).
4. Нажать «Оформить заказ».
5. Ожидаемо: корзина очищается, появляется сообщение вида «Заказ оформлен! Сэкономлено N ₽», карточка «ЭКОНОМИЯ ЗА НЕДЕЛЮ» на этом же экране обновляет цифры без перезагрузки экрана.
6. Повторно нажать «Оформить заказ» на пустой корзине — кнопка должна быть неактивна (disabled).

- [ ] **Step 7: Commit**

```bash
git add x5mobile/src/components/screens/savings-view.tsx x5mobile/src/app/index.tsx
git commit -m "feat: add checkout button to weekly basket, refresh economy on order placed"
```
