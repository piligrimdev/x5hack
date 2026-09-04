# Basket AI Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic "weekly basket" suggestion built from a user's own receipt history, plus a text-instruction AI assistant (OpenRouter tool-calling) that adds/removes/adjusts items in that basket — both embedded into the existing `savings-view.tsx` screen, no new screen or DB table.

**Architecture:** New `basket` domain inside the existing `webx5` FastAPI package (RSI: `crud/basket.py` → `services/basket_assistant.py` → `routes/basket.py`), stateless (the frontend holds the current basket list and resends it with every assistant request). Frontend: one new hook (`useBasket`) plus a card + text input added to `savings-view.tsx`.

**Tech Stack:** FastAPI + SQLAlchemy (sync) + Pydantic v2, OpenRouter (`deepseek/deepseek-chat`, verified to support structured tool-calling — see Task 1) via `httpx`, Expo/React Native/TypeScript.

**Spec:** `docs/superpowers/specs/2026-09-04-basket-ai-assistant-design.md`

## Global Constraints

- RSI layering: `crud/` (data access) → `services/` (business logic, no SQL) → `routes/` (schema + session → service only). No SQL in routes, no repo construction inside services (constructor DI).
- No new DB table — the basket is stateless per-request; the frontend resends its current item list on every `POST /basket/assistant` call.
- `forbidden_categories` (алкоголь/детское питание) from `synth/challenges.py` does **not** apply here — the user is explicitly requesting their own basket contents, not receiving a proactive recommendation.
- A malformed/failed/empty LLM response must never silently pass through as a valid basket change — always fall back to the unchanged basket + a message (`applied=false`).
- Dependencies: Poetry only (`web/pyproject.toml` + lock), no ad-hoc `pip install`.
- Auth: `CurrentUserUUID` (existing `webx5.dependencies.auth`) on both new endpoints — no new auth pattern.
- No JS/TS test runner exists in `x5mobile/` (no jest, no `*.test.ts*` files anywhere in the repo) — frontend tasks are verified manually (Expo web/emulator), not with automated tests. Backend tasks follow existing project convention: `services/`/`routes/` get pytest coverage with mocked repos/HTTP; `crud/` (raw SQL/SQLAlchemy) and `web/scripts/*.py` do not have automated tests anywhere in this repo today — verified manually instead, same as every other file in those two locations.

---

### Task 1: Verify OpenRouter tool-calling (already confirmed working)

**Files:** none (no code produced by this task — a recorded verification).

Already run live during planning against the real `OPENROUTER_API_KEY` in `.env`. Result: `deepseek/deepseek-chat` correctly returns structured `tool_calls` (not just text) when given a `tools` array, including handling two distinct intents ("убери шоколадку и добавь 2 кефира") in a single call with correctly-typed arguments. Confirmed response shape:

```json
{
  "choices": [{
    "message": {
      "content": null,
      "tool_calls": [
        {"type": "function", "id": "call_...", "function": {"name": "remove_item", "arguments": "{\"sku_id\": \"sku_0042\"}"}},
        {"type": "function", "id": "call_...", "function": {"name": "add_item", "arguments": "{\"sku_id\": \"sku_0001\", \"quantity\": 2}"}}
      ]
    }
  }]
}
```

This confirms the design in the spec is buildable with the default model — no fallback model needed. `core/llm.py` (Task 3) is written directly against this exact response shape.

- [ ] **Step 1: Re-run the verification once, to confirm your own environment's `OPENROUTER_API_KEY` also works**

```bash
cd /Users/dimonzhi/Documents/proga/x5hack
python3 - <<'PYEOF'
import os, json
from dotenv import load_dotenv
load_dotenv(".env")
import requests

api_key = os.environ["OPENROUTER_API_KEY"]
tools = [{
    "type": "function",
    "function": {
        "name": "add_item",
        "description": "Add a product to the basket by its catalog SKU id",
        "parameters": {
            "type": "object",
            "properties": {"sku_id": {"type": "string"}, "quantity": {"type": "integer"}},
            "required": ["sku_id", "quantity"],
        },
    },
}]
resp = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    json={
        "model": "deepseek/deepseek-chat",
        "messages": [
            {"role": "system", "content": "Каталог: sku_0000=Молоко."},
            {"role": "user", "content": "добавь 2 молока"},
        ],
        "tools": tools,
        "tool_choice": "auto",
    },
    timeout=60,
)
msg = resp.json()["choices"][0]["message"]
assert msg.get("tool_calls"), f"expected tool_calls, got: {msg}"
print("OK — tool_calls present:", json.dumps(msg["tool_calls"], ensure_ascii=False))
PYEOF
```

Expected: prints `OK — tool_calls present: ...` with an `add_item` call for `sku_0000` quantity 2. If this fails (no `tool_calls`, or an HTTP error), STOP and re-open the design decision in the spec's "LLM и риски" section before proceeding to Task 3 — a different OpenRouter model would need to be substituted.

- [ ] **Step 2: No commit** — this task produces no file changes.

---

### Task 2: Fix `seed_receipts.py` so a demo login has real purchase history

**Files:**
- Modify: `web/scripts/seed_receipts.py`

**Interfaces:**
- Produces: after re-seeding, `users` contains one row per synthetic `user_id` in the seed file, with `id` equal to the same `uuid5` used for that user's `loyalty_cards.id` (so `receipts.loyalty_card_id`, which is actually an FK to `users.id`, resolves correctly — see migration `e3f4a5b6c7d8_fix_receipts_loyalty_card_fk`). A demo tester can `POST /login` with the printed phone number and land on that exact user's `user_id`.

- [ ] **Step 1: Add the phone-generation helper and `User` import**

In `web/scripts/seed_receipts.py`, after the existing imports block (after `from webx5.entities.receipt import Receipt, ReceiptItem  # noqa: E402`), add:

```python
from webx5.entities.user import User  # noqa: E402
from webx5.utils.auth import normalize_phone  # noqa: E402
```

And add `import hashlib` to the top import block (alongside the existing `import json`).

Then, after the `_receipt_uuid` function definition, add:

```python
def _synthetic_phone(user_id_str: str) -> str:
    """Deterministic, valid RU mobile number for a synthetic user — lets a
    demo login as this user via the real /login flow (POST /login with this
    phone). +7900 is a real MegaFon mobile range; the 7-digit suffix is
    derived from user_id_str so re-running the seed always produces the
    same phone for the same synthetic user."""
    digest = hashlib.sha256(user_id_str.encode("utf-8")).hexdigest()
    suffix = str(int(digest[:8], 16) % 10_000_000).zfill(7)
    return normalize_phone(f"+7900{suffix}")
```

- [ ] **Step 2: Verify the helper produces valid, idempotent phone numbers**

```bash
python3 - <<'PYEOF'
import hashlib
import phonenumbers

def normalize_phone(raw: str) -> str:
    parsed = phonenumbers.parse(raw, "RU")
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError(f"Invalid phone number: {raw!r}")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)

def synthetic_phone(user_id_str: str) -> str:
    digest = hashlib.sha256(user_id_str.encode("utf-8")).hexdigest()
    suffix = str(int(digest[:8], 16) % 10_000_000).zfill(7)
    return normalize_phone(f"+7900{suffix}")

for uid in ["c9f51e79-b5e1-4236-9d58-dbc84998a999", "7f7e70d8-178b-421b-80a3-d9cec8b73ad9"]:
    p = synthetic_phone(uid)
    assert p == normalize_phone(p)
    print(uid, "->", p)
PYEOF
```

Expected: two `uid -> +79...` lines, no `AssertionError`, no `ValueError`. (This reproduces the exact algorithm added in Step 1 — `webx5.utils.auth.normalize_phone` uses the same `phonenumbers` library underneath, so this is a faithful standalone check without needing the full script's DB-connecting imports.)

- [ ] **Step 3: Create the `User` row alongside the `LoyaltyCard`, and track/report it**

In `main()`, change the counters line:

```python
    users_processed = cards_created = receipts_created = receipts_skipped = items_created = 0
```

to:

```python
    users_processed = users_created = cards_created = receipts_created = receipts_skipped = items_created = 0
    demo_logins: list[tuple[str, str]] = []
```

Find this exact block (the `if not card:` body ends with `cards_created += 1`, then the next line is `store_id = _get_store_id(chain, district)`):

```python
                    session.add(card)
                    session.flush()
                    cards_created += 1

                store_id = _get_store_id(chain, district)
```

Insert the new `User`-creation block between those two lines — after `cards_created += 1` (dedented back to the same 16-space indentation as `card = session.get(...)`/`store_id = ...`, i.e. NOT inside the `if not card:` body) and before `store_id = _get_store_id(...)`:

```python
                    session.add(card)
                    session.flush()
                    cards_created += 1

                # Create matching User row so a demo login (POST /login with
                # this phone) resolves to this same id — receipts.loyalty_card_id
                # is actually a FK to users.id, not loyalty_cards.id.
                user = session.get(User, loyalty_card_id)
                if not user:
                    phone = _synthetic_phone(user_id_str)
                    user = User(id=loyalty_card_id, phone=phone)
                    session.add(user)
                    session.flush()
                    users_created += 1
                    if len(demo_logins) < 5:
                        demo_logins.append((user_id_str, phone))

                store_id = _get_store_id(chain, district)
```

- [ ] **Step 4: Report the demo logins and updated counts in the final summary**

Replace:

```python
    print(
        f"Done. Users processed: {users_processed}, "
        f"Cards created: {cards_created}, "
        f"Receipts created: {receipts_created}, "
        f"Receipts skipped: {receipts_skipped}, "
        f"Items created: {items_created}"
    )
```

with:

```python
    print(
        f"Done. Users processed: {users_processed}, "
        f"Users created: {users_created}, "
        f"Cards created: {cards_created}, "
        f"Receipts created: {receipts_created}, "
        f"Receipts skipped: {receipts_skipped}, "
        f"Items created: {items_created}"
    )
    if demo_logins:
        print("Demo logins (POST /login with one of these phones):")
        for user_id_str, phone in demo_logins:
            print(f"  user_id={user_id_str}  phone={phone}")
```

- [ ] **Step 5: Run the seed script against a real database and confirm**

This requires the project's Postgres running (see `README.md`/`docker-compose.yml` — already covered by the existing project setup, not part of this task). With `DATABASE_URL` and `SEED_FILE_PATH` set per the script's existing docstring:

```bash
cd web
poetry run python scripts/seed_receipts.py
```

Expected: the final summary line shows `Users created: N` with `N > 0` (equal to however many synthetic users hadn't already been seeded), followed by up to 5 `user_id=... phone=...` lines. Then confirm one of those phones can actually log in:

```bash
curl -s -X POST http://localhost:8000/login -H "Content-Type: application/json" \
  -d '{"phone": "<one of the printed phones>"}'
```

Expected: `200` with `{"access_token": "...", "refresh_token": "..."}` (refresh in a Set-Cookie header) — not a `404 User not found`.

- [ ] **Step 6: Commit**

```bash
git add web/scripts/seed_receipts.py
git commit -m "$(cat <<'EOF'
Seed a matching User row per synthetic loyalty card

receipts.loyalty_card_id is actually an FK to users.id (not
loyalty_cards.id, per the earlier e3f4a5b6c7d8 migration), but this
script only ever created loyalty_cards rows — so a real demo login had
no receipts of its own to build a purchase-history-based basket from.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NDtuwfEXNASSVZjNZFVoxy
EOF
)"
```

---

### Task 3: `core/llm.py` — OpenRouter tool-calling wrapper

**Files:**
- Create: `web/src/webx5/core/llm.py`
- Test: `web/tests/webx5/core/__init__.py` (new, empty — mirrors `tests/webx5/{routes,services,utils}/__init__.py`)
- Test: `web/tests/webx5/core/test_llm.py`
- Modify: `web/pyproject.toml`
- Modify: `.env.example`

**Interfaces:**
- Produces: `ToolCall` (dataclass: `name: str`, `arguments: dict`), `call_openrouter_tools(model: str, system: str, user: str, tools: list[dict], api_key: str | None = None, timeout: float = 30.0) -> list[ToolCall]` — raises `RuntimeError` if no API key resolvable, raises on HTTP/network failure (`httpx.HTTPStatusError` etc.; caller decides fallback), returns `[]` if the model made no tool calls or every tool call was malformed (unparseable `arguments` JSON, missing `name`).

- [ ] **Step 1: Add `httpx` as a main dependency**

In `web/pyproject.toml`, in the `dependencies = [...]` array (not the `[dependency-groups] dev` one — that stays as-is), add:

```toml
    "httpx>=0.27.0,<1.0.0",
```

Run:

```bash
cd web && poetry lock --no-update && poetry install
```

Expected: lockfile updates, install succeeds, no errors.

- [ ] **Step 2: Add `OPENROUTER_API_KEY` to `.env.example`**

In `.env.example`, after the `TERMINAL_TOKEN=change-me-in-production` line, add:

```
OPENROUTER_API_KEY=change-me-in-production
```

- [ ] **Step 3: Write the failing tests**

Create `web/tests/webx5/core/__init__.py` (empty file).

Create `web/tests/webx5/core/test_llm.py`:

```python
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from webx5.core.llm import ToolCall, call_openrouter_tools


def _fake_response(tool_calls: list[dict] | None) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"choices": [{"message": {"tool_calls": tool_calls}}]}
    return resp


def test_call_openrouter_tools_parses_valid_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_calls = [
        {"function": {"name": "add_item", "arguments": json.dumps({"sku_id": "sku_1", "quantity": 2})}},
    ]
    monkeypatch.setattr("webx5.core.llm.httpx.post", lambda *a, **k: _fake_response(fake_calls))

    result = call_openrouter_tools(model="fake/model", system="s", user="u", tools=[], api_key="k")

    assert len(result) == 1
    assert result[0].name == "add_item"
    assert result[0].arguments == {"sku_id": "sku_1", "quantity": 2}


def test_call_openrouter_tools_returns_empty_list_when_no_tool_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("webx5.core.llm.httpx.post", lambda *a, **k: _fake_response(None))

    result = call_openrouter_tools(model="fake/model", system="s", user="u", tools=[], api_key="k")

    assert result == []


def test_call_openrouter_tools_skips_malformed_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_calls = [{"function": {"name": "add_item", "arguments": "not json"}}]
    monkeypatch.setattr("webx5.core.llm.httpx.post", lambda *a, **k: _fake_response(fake_calls))

    result = call_openrouter_tools(model="fake/model", system="s", user="u", tools=[], api_key="k")

    assert result == []


def test_call_openrouter_tools_skips_calls_missing_a_name(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_calls = [{"function": {"arguments": "{}"}}]
    monkeypatch.setattr("webx5.core.llm.httpx.post", lambda *a, **k: _fake_response(fake_calls))

    result = call_openrouter_tools(model="fake/model", system="s", user="u", tools=[], api_key="k")

    assert result == []


def test_call_openrouter_tools_raises_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        call_openrouter_tools(model="fake/model", system="s", user="u", tools=[], api_key=None)
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
cd web && poetry run pytest tests/webx5/core/test_llm.py -v
```

Expected: `ModuleNotFoundError: No module named 'webx5.core.llm'` (or import error) — the module doesn't exist yet.

- [ ] **Step 5: Write `core/llm.py`**

```python
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)


def call_openrouter_tools(
    model: str,
    system: str,
    user: str,
    tools: list[dict],
    api_key: str | None = None,
    timeout: float = 30.0,
) -> list[ToolCall]:
    """Call OpenRouter chat completions with tool-calling enabled.

    Returns the parsed tool calls the model made — an empty list if it made
    none, or if every returned tool call was malformed (unparseable
    arguments, missing name). Network/HTTP errors DO raise (httpx's own
    exceptions) — the caller decides what fallback behavior that implies;
    this function only absorbs "the model responded but the response
    doesn't make sense," not connectivity failures.
    """
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (env var, or pass api_key explicitly)")

    resp = httpx.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()

    raw_calls = data["choices"][0]["message"].get("tool_calls") or []
    result: list[ToolCall] = []
    for call in raw_calls:
        fn = call.get("function", {})
        name = fn.get("name")
        if not name:
            continue
        try:
            arguments = json.loads(fn.get("arguments", "{}"))
        except json.JSONDecodeError:
            continue
        result.append(ToolCall(name=name, arguments=arguments))
    return result
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd web && poetry run pytest tests/webx5/core/test_llm.py -v
```

Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add web/src/webx5/core/llm.py web/tests/webx5/core/ web/pyproject.toml web/poetry.lock .env.example
git commit -m "$(cat <<'EOF'
Add OpenRouter tool-calling wrapper (core/llm.py)

Thin sync wrapper around OpenRouter's chat completions endpoint with
tools=[...] — verified live against deepseek/deepseek-chat during
planning (see docs/superpowers/plans/2026-09-04-basket-ai-assistant.md
Task 1). Foundation for the basket assistant's add/remove/set_quantity
tool calls.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NDtuwfEXNASSVZjNZFVoxy
EOF
)"
```

---

### Task 4: `schemas/basket.py` + `crud/basket.py` (BasketRepository)

**Files:**
- Create: `web/src/webx5/schemas/basket.py`
- Create: `web/src/webx5/crud/basket.py`

**Interfaces:**
- Consumes: `webx5.entities.product.Product` (`id`, `sku_id`, `name`, `current_price`, `category_id`), `webx5.entities.receipt.Receipt` (`id`, `loyalty_card_id`, `purchase_date`), `webx5.entities.receipt.ReceiptItem` (`id`, `receipt_id`, `product_id`, `quantity`), `webx5.schemas.types.JsonDecimal`.
- Produces: `BasketItem(product_id: UUID, name: str, quantity: int, price: JsonDecimal)`, `SuggestedBasketResponse(items: list[BasketItem])`, `BasketItemIn(product_id: UUID, quantity: int)`, `AssistantRequest(items: list[BasketItemIn], instruction: str)`, `AssistantResponse(items: list[BasketItem], applied: bool, message: str | None)`. `BasketRepository.suggest_items(session, user_id: UUID) -> list[tuple[Product, int]]`, `BasketRepository.get_full_catalog(session) -> list[Product]`.

No dedicated unit tests for this task — matches this repo's existing convention: no `tests/webx5/schemas/` or `tests/webx5/crud/` directory exists anywhere today (schemas are exercised through route-level 422 tests, e.g. `test_catalog.py::TestCreateProduct::test_invalid_price_returns_422`; repos are exercised indirectly through service tests with `MagicMock(spec=Repository)`, e.g. `test_receipt_service.py`). This task's schema validation is verified in Task 6's route tests; the repository's SQL is verified manually in Task 6's manual check and mocked in Task 5's service tests.

- [ ] **Step 1: Write `schemas/basket.py`**

```python
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from webx5.schemas.types import JsonDecimal


class BasketItem(BaseModel):
    product_id: uuid.UUID
    name: str
    quantity: int
    price: JsonDecimal


class SuggestedBasketResponse(BaseModel):
    items: list[BasketItem]


class BasketItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1)


class AssistantRequest(BaseModel):
    items: list[BasketItemIn]
    instruction: str = Field(min_length=1, max_length=500)


class AssistantResponse(BaseModel):
    items: list[BasketItem]
    applied: bool
    message: str | None = None
```

- [ ] **Step 2: Write `crud/basket.py`**

```python
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from webx5.entities.product import Product
from webx5.entities.receipt import Receipt, ReceiptItem

# A product must repeat at least this often per week (on average, over the
# user's own full receipt history) to be suggested for the weekly basket —
# 0.5 means "roughly once every two weeks or more often". Deliberately
# conservative: the basket should read as "what you actually keep buying",
# not every item ever bought once. Tune against real seeded data if the
# suggested list reads as too sparse/too noisy once Task 2's seed is live.
MIN_WEEKLY_FREQUENCY = 0.5


class BasketRepository:
    def suggest_items(self, session: Session, user_id: uuid.UUID) -> list[tuple[Product, int]]:
        """Return (product, suggested_quantity) pairs for products this user
        buys with at least MIN_WEEKLY_FREQUENCY cadence, based on their own
        full receipt history. suggested_quantity is the rounded average
        quantity per purchase (minimum 1). Empty list if the user has no
        receipts at all (min/max purchase_date both None)."""
        min_date, max_date = session.execute(
            select(func.min(Receipt.purchase_date), func.max(Receipt.purchase_date)).where(
                Receipt.loyalty_card_id == user_id
            )
        ).one()
        if min_date is None or max_date is None:
            return []

        span_weeks = max((max_date - min_date).days / 7, 1.0)

        rows = session.execute(
            select(
                Product,
                func.count(ReceiptItem.id).label("purchase_count"),
                func.avg(ReceiptItem.quantity).label("avg_quantity"),
            )
            .join(ReceiptItem, ReceiptItem.product_id == Product.id)
            .join(Receipt, Receipt.id == ReceiptItem.receipt_id)
            .where(Receipt.loyalty_card_id == user_id)
            .group_by(Product.id)
        ).all()

        result: list[tuple[Product, int]] = []
        for product, purchase_count, avg_quantity in rows:
            weekly_frequency = purchase_count / span_weeks
            if weekly_frequency >= MIN_WEEKLY_FREQUENCY:
                result.append((product, max(1, round(avg_quantity))))
        return result

    def get_full_catalog(self, session: Session) -> list[Product]:
        return list(session.scalars(select(Product)))
```

- [ ] **Step 3: Sanity-check the module imports cleanly**

```bash
cd web && poetry run python -c "from webx5.crud.basket import BasketRepository; from webx5.schemas.basket import AssistantRequest; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add web/src/webx5/schemas/basket.py web/src/webx5/crud/basket.py
git commit -m "$(cat <<'EOF'
Add basket schemas and BasketRepository

BasketRepository.suggest_items aggregates a user's own full receipt
history into a weekly-cadence product list, entirely in SQL — no LLM
involved, same principle as synth/challenges.py's deterministic
spend_threshold/category_expansion builders.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NDtuwfEXNASSVZjNZFVoxy
EOF
)"
```

---

### Task 5: `services/basket_assistant.py` (BasketService)

**Files:**
- Create: `web/src/webx5/services/basket_assistant.py`
- Test: `web/tests/webx5/services/test_basket_assistant.py`

**Interfaces:**
- Consumes: `webx5.crud.basket.BasketRepository` (`suggest_items`, `get_full_catalog`), `webx5.core.llm.call_openrouter_tools`, `webx5.core.llm.ToolCall`, `webx5.schemas.basket.{BasketItem, BasketItemIn, AssistantResponse}`.
- Produces: `BasketService(repo: BasketRepository, model: str = "deepseek/deepseek-chat")`, `.suggest(session, user_id: UUID) -> list[BasketItem]`, `.apply_instruction(session, items: list[BasketItemIn], instruction: str, api_key: str | None = None) -> AssistantResponse`.

- [ ] **Step 1: Write the failing tests**

Create `web/tests/webx5/services/test_basket_assistant.py`:

```python
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from webx5.core.llm import ToolCall
from webx5.crud.basket import BasketRepository
from webx5.entities.product import Product
from webx5.schemas.basket import BasketItemIn
from webx5.services.basket_assistant import BasketService


def _make_product(sku_id: str, name: str, price: str = "100.00") -> Product:
    p = Product()
    p.id = uuid.uuid4()
    p.sku_id = sku_id
    p.name = name
    p.current_price = Decimal(price)
    p.category_id = uuid.uuid4()
    p.brand_id = None
    return p


@pytest.fixture()
def repo() -> MagicMock:
    return MagicMock(spec=BasketRepository)


@pytest.fixture()
def service(repo: MagicMock) -> BasketService:
    return BasketService(repo=repo, model="fake/model")


@pytest.fixture()
def session() -> MagicMock:
    return MagicMock()


class TestSuggest:
    def test_maps_repo_pairs_to_basket_items(
        self, service: BasketService, repo: MagicMock, session: MagicMock
    ) -> None:
        product = _make_product("sku_0001", "Молоко", price="89.90")
        repo.suggest_items.return_value = [(product, 2)]

        items = service.suggest(session, uuid.uuid4())

        assert len(items) == 1
        assert items[0].product_id == product.id
        assert items[0].name == "Молоко"
        assert items[0].quantity == 2
        assert items[0].price == Decimal("89.90")

    def test_empty_history_returns_empty_list(
        self, service: BasketService, repo: MagicMock, session: MagicMock
    ) -> None:
        repo.suggest_items.return_value = []
        assert service.suggest(session, uuid.uuid4()) == []


class TestApplyInstruction:
    def test_add_item_tool_call_adds_product(
        self, service: BasketService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        monkeypatch.setattr(
            "webx5.services.basket_assistant.call_openrouter_tools",
            lambda **kwargs: [ToolCall(name="add_item", arguments={"sku_id": "sku_0001", "quantity": 2})],
        )

        result = service.apply_instruction(session, items=[], instruction="добавь молоко")

        assert result.applied is True
        assert len(result.items) == 1
        assert result.items[0].product_id == milk.id
        assert result.items[0].quantity == 2

    def test_remove_item_tool_call_removes_existing_item(
        self, service: BasketService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        monkeypatch.setattr(
            "webx5.services.basket_assistant.call_openrouter_tools",
            lambda **kwargs: [ToolCall(name="remove_item", arguments={"sku_id": "sku_0001"})],
        )

        result = service.apply_instruction(
            session, items=[BasketItemIn(product_id=milk.id, quantity=1)], instruction="убери молоко"
        )

        assert result.applied is True
        assert result.items == []

    def test_set_quantity_tool_call_overwrites_quantity(
        self, service: BasketService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        monkeypatch.setattr(
            "webx5.services.basket_assistant.call_openrouter_tools",
            lambda **kwargs: [ToolCall(name="set_quantity", arguments={"sku_id": "sku_0001", "quantity": 5})],
        )

        result = service.apply_instruction(
            session, items=[BasketItemIn(product_id=milk.id, quantity=1)], instruction="пусть будет 5 молока"
        )

        assert result.items[0].quantity == 5

    def test_no_tool_calls_returns_unchanged_basket_with_message(
        self, service: BasketService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", lambda **kwargs: [])

        result = service.apply_instruction(
            session, items=[BasketItemIn(product_id=milk.id, quantity=1)], instruction="???"
        )

        assert result.applied is False
        assert result.message == "Не поняла запрос, попробуй иначе"
        assert result.items[0].quantity == 1

    def test_llm_failure_returns_unchanged_basket_with_message(
        self, service: BasketService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]

        def _raise(**kwargs):
            raise RuntimeError("network error")

        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", _raise)

        result = service.apply_instruction(
            session, items=[BasketItemIn(product_id=milk.id, quantity=1)], instruction="добавь что-нибудь"
        )

        assert result.applied is False
        assert result.items[0].quantity == 1

    def test_unknown_sku_in_tool_call_is_ignored(
        self, service: BasketService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        monkeypatch.setattr(
            "webx5.services.basket_assistant.call_openrouter_tools",
            lambda **kwargs: [ToolCall(name="add_item", arguments={"sku_id": "sku_9999", "quantity": 1})],
        )

        result = service.apply_instruction(session, items=[], instruction="добавь что-то странное")

        assert result.applied is False
        assert result.items == []

    def test_item_with_unknown_product_id_in_request_is_dropped(
        self, service: BasketService, repo: MagicMock, session: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        milk = _make_product("sku_0001", "Молоко")
        repo.get_full_catalog.return_value = [milk]
        monkeypatch.setattr("webx5.services.basket_assistant.call_openrouter_tools", lambda **kwargs: [])

        result = service.apply_instruction(
            session, items=[BasketItemIn(product_id=uuid.uuid4(), quantity=1)], instruction="???"
        )

        assert result.items == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd web && poetry run pytest tests/webx5/services/test_basket_assistant.py -v
```

Expected: `ModuleNotFoundError: No module named 'webx5.services.basket_assistant'`.

- [ ] **Step 3: Write `services/basket_assistant.py`**

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

logger = structlog.get_logger(__name__)

CANNOT_UNDERSTAND_MESSAGE = "Не поняла запрос, попробуй иначе"
LLM_FAILURE_MESSAGE = "Не получилось обработать запрос, попробуй ещё раз"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "add_item",
            "description": "Add a product to the basket, or increase its quantity if already present",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku_id": {"type": "string", "description": "catalog SKU id, e.g. sku_0042"},
                    "quantity": {"type": "integer", "description": "how many units to add"},
                },
                "required": ["sku_id", "quantity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_item",
            "description": "Remove a product from the basket entirely",
            "parameters": {
                "type": "object",
                "properties": {"sku_id": {"type": "string", "description": "catalog SKU id, e.g. sku_0042"}},
                "required": ["sku_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_quantity",
            "description": "Set the exact quantity of a product already in the basket",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku_id": {"type": "string", "description": "catalog SKU id, e.g. sku_0042"},
                    "quantity": {"type": "integer", "description": "the new exact quantity"},
                },
                "required": ["sku_id", "quantity"],
            },
        },
    },
]


class BasketService:
    def __init__(self, repo: BasketRepository, model: str = "deepseek/deepseek-chat") -> None:
        self.repo = repo
        self.model = model

    def suggest(self, session: Session, user_id: uuid.UUID) -> list[BasketItem]:
        pairs = self.repo.suggest_items(session, user_id)
        return [self._to_basket_item(p, qty) for p, qty in pairs]

    def apply_instruction(
        self,
        session: Session,
        items: list[BasketItemIn],
        instruction: str,
        api_key: str | None = None,
    ) -> AssistantResponse:
        catalog = self.repo.get_full_catalog(session)
        catalog_by_id: dict[uuid.UUID, Product] = {p.id: p for p in catalog}
        catalog_by_sku: dict[str, Product] = {p.sku_id: p for p in catalog}

        current: dict[uuid.UUID, int] = {
            item.product_id: item.quantity for item in items if item.product_id in catalog_by_id
        }

        system = self._build_system_prompt(current, catalog_by_id)
        try:
            tool_calls = call_openrouter_tools(
                model=self.model, system=system, user=instruction, tools=TOOLS, api_key=api_key
            )
        except Exception as e:  # noqa: BLE001 — any LLM failure must fall back, not propagate
            logger.warning("basket_assistant.llm_call_failed", error=str(e))
            return self._response(current, catalog_by_id, applied=False, message=LLM_FAILURE_MESSAGE)

        applied_any = False
        for call in tool_calls:
            sku_id = call.arguments.get("sku_id")
            product = catalog_by_sku.get(sku_id) if isinstance(sku_id, str) else None
            if product is None:
                continue
            if call.name == "add_item":
                quantity = call.arguments.get("quantity")
                if not isinstance(quantity, int) or quantity < 1:
                    continue
                current[product.id] = current.get(product.id, 0) + quantity
                applied_any = True
            elif call.name == "remove_item":
                if current.pop(product.id, None) is not None:
                    applied_any = True
            elif call.name == "set_quantity":
                quantity = call.arguments.get("quantity")
                if not isinstance(quantity, int):
                    continue
                if quantity < 1:
                    current.pop(product.id, None)
                else:
                    current[product.id] = quantity
                applied_any = True

        if not applied_any:
            logger.info("basket_assistant.no_applicable_tool_calls", instruction=instruction)
            return self._response(current, catalog_by_id, applied=False, message=CANNOT_UNDERSTAND_MESSAGE)
        return self._response(current, catalog_by_id, applied=True, message=None)

    def _build_system_prompt(self, current: dict[uuid.UUID, int], catalog_by_id: dict[uuid.UUID, Product]) -> str:
        current_lines = (
            "\n".join(f"- {catalog_by_id[pid].sku_id} ({catalog_by_id[pid].name}): {qty} шт" for pid, qty in current.items())
            or "(пусто)"
        )
        catalog_lines = "\n".join(f"- {p.sku_id}: {p.name}" for p in catalog_by_id.values())
        return (
            "Ты — ассистент корзины покупок в приложении лояльности X5. "
            "Пользователь просит добавить или убрать товары из своей текущей корзины. "
            "Используй ТОЛЬКО доступные функции (add_item/remove_item/set_quantity), "
            "передавай sku_id ровно как он указан в каталоге ниже, ничего не выдумывай.\n\n"
            f"Текущая корзина:\n{current_lines}\n\n"
            f"Каталог доступных товаров:\n{catalog_lines}"
        )

    @staticmethod
    def _to_basket_item(product: Product, quantity: int) -> BasketItem:
        return BasketItem(
            product_id=product.id, name=product.name, quantity=quantity, price=Decimal(str(product.current_price))
        )

    def _response(
        self,
        current: dict[uuid.UUID, int],
        catalog_by_id: dict[uuid.UUID, Product],
        applied: bool,
        message: str | None,
    ) -> AssistantResponse:
        items = [self._to_basket_item(catalog_by_id[pid], qty) for pid, qty in current.items()]
        return AssistantResponse(items=items, applied=applied, message=message)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd web && poetry run pytest tests/webx5/services/test_basket_assistant.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add web/src/webx5/services/basket_assistant.py web/tests/webx5/services/test_basket_assistant.py
git commit -m "$(cat <<'EOF'
Add BasketService (suggest + LLM tool-calling assistant)

apply_instruction applies parsed tool calls itself (never trusts the
model to restate the whole list correctly) and always falls back to
the unchanged basket + a message on any LLM failure or unusable
response, same principle as synth/challenges.py's generic_fallback.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NDtuwfEXNASSVZjNZFVoxy
EOF
)"
```

---

### Task 6: `routes/basket.py` + wiring + registration

**Files:**
- Create: `web/src/webx5/core/basket.py`
- Create: `web/src/webx5/routes/basket.py`
- Modify: `web/src/webx5/core/server.py`
- Test: `web/tests/webx5/routes/test_basket.py`

**Interfaces:**
- Consumes: `webx5.crud.basket.BasketRepository`, `webx5.services.basket_assistant.BasketService`, `webx5.dependencies.auth.CurrentUserUUID`, `webx5.dependencies.db.SessionDep`, `webx5.schemas.basket.{AssistantRequest, AssistantResponse, SuggestedBasketResponse}`.
- Produces: `GET /basket/suggested`, `POST /basket/assistant` — both registered on `app` in `core/server.py`.

- [ ] **Step 1: Write the failing tests**

Create `web/tests/webx5/routes/test_basket.py`:

```python
import os
import uuid
from decimal import Decimal
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://postgres:password@localhost:5432/x5hack_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_TTL_DAYS", "7")
os.environ.setdefault("JWT_REFRESH_TTL_DAYS", "14")
os.environ.setdefault("TERMINAL_TOKEN", "test-terminal-token")

from fastapi.testclient import TestClient  # noqa: E402

from webx5.core.server import app  # noqa: E402
from webx5.schemas.basket import AssistantResponse, BasketItem  # noqa: E402
from webx5.utils.auth import encode_access_jwt  # noqa: E402

client = TestClient(app)


def _token() -> str:
    return encode_access_jwt(uuid.uuid4())


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestGetSuggestedBasket:
    def test_returns_items(self) -> None:
        item = BasketItem(product_id=uuid.uuid4(), name="Молоко", quantity=2, price=Decimal("89.90"))
        with patch("webx5.services.basket_assistant.BasketService.suggest", return_value=[item]):
            resp = client.get("/basket/suggested", headers=_bearer(_token()))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["name"] == "Молоко"

    def test_requires_auth(self) -> None:
        resp = client.get("/basket/suggested")
        assert resp.status_code == 401


class TestPostBasketAssistant:
    def test_returns_updated_items(self) -> None:
        item = BasketItem(product_id=uuid.uuid4(), name="Кефир", quantity=2, price=Decimal("75.00"))
        fake_response = AssistantResponse(items=[item], applied=True, message=None)
        with patch(
            "webx5.services.basket_assistant.BasketService.apply_instruction",
            return_value=fake_response,
        ):
            resp = client.post(
                "/basket/assistant",
                json={"items": [], "instruction": "добавь кефир"},
                headers=_bearer(_token()),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["applied"] is True
        assert body["items"][0]["name"] == "Кефир"

    def test_requires_auth(self) -> None:
        resp = client.post("/basket/assistant", json={"items": [], "instruction": "x"})
        assert resp.status_code == 401

    def test_rejects_empty_instruction(self) -> None:
        resp = client.post(
            "/basket/assistant",
            json={"items": [], "instruction": ""},
            headers=_bearer(_token()),
        )
        assert resp.status_code == 422
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd web && poetry run pytest tests/webx5/routes/test_basket.py -v
```

Expected: `ModuleNotFoundError` or `404` — `/basket/*` routes don't exist yet.

- [ ] **Step 3: Write `core/basket.py`**

```python
from webx5.crud.basket import BasketRepository
from webx5.services.basket_assistant import BasketService

basket_repo = BasketRepository()
basket_service = BasketService(repo=basket_repo)
```

- [ ] **Step 4: Write `routes/basket.py`**

```python
from __future__ import annotations

from fastapi import APIRouter

from webx5.dependencies.auth import CurrentUserUUID
from webx5.dependencies.db import SessionDep
from webx5.schemas.basket import AssistantRequest, AssistantResponse, SuggestedBasketResponse

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
```

- [ ] **Step 5: Register the router in `core/server.py`**

In `web/src/webx5/core/server.py`, add the import next to the other route imports:

```python
from webx5.routes.auth import auth_router
```

becomes (insert alphabetically before `catalog_router`):

```python
from webx5.routes.auth import auth_router
from webx5.routes.basket import basket_router
```

And add `app.include_router(basket_router)` next to the other `include_router` calls:

```python
app.include_router(auth_router)
```

becomes:

```python
app.include_router(auth_router)
app.include_router(basket_router)
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd web && poetry run pytest tests/webx5/routes/test_basket.py -v
```

Expected: 5 passed.

- [ ] **Step 7: Run the full backend test suite**

```bash
cd web && poetry run pytest -v
```

Expected: all pass (existing + new).

- [ ] **Step 8: Manually verify the SQL in `BasketRepository.suggest_items` against real seeded data**

Requires Task 2 already run against a real DB with actual receipts.

```bash
cd web
poetry run python -c "
from webx5.core.db import db
from webx5.crud.basket import BasketRepository
import uuid

repo = BasketRepository()
with db.get_sync_session() as session:
    from webx5.entities.user import User
    from sqlalchemy import select
    user_id = session.scalar(select(User.id).limit(1))
    items = repo.suggest_items(session, user_id)
    print(f'user_id={user_id}, suggested {len(items)} products:')
    for product, qty in items:
        print(f'  {product.name}: {qty}')
"
```

Expected: a non-crashing list (possibly empty if that particular user's history is thin — try a few different `.limit(1)` offsets, or query for a user with many receipts, if the first one is empty). If every user comes back empty, revisit `MIN_WEEKLY_FREQUENCY` in `crud/basket.py` — lower it and re-run.

- [ ] **Step 9: Commit**

```bash
git add web/src/webx5/core/basket.py web/src/webx5/routes/basket.py web/src/webx5/core/server.py web/tests/webx5/routes/test_basket.py
git commit -m "$(cat <<'EOF'
Wire up GET /basket/suggested and POST /basket/assistant

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NDtuwfEXNASSVZjNZFVoxy
EOF
)"
```

---

### Task 7: Frontend — `useBasket` hook

**Files:**
- Create: `x5mobile/src/hooks/useBasket.ts`

**Interfaces:**
- Consumes: `apiFetch<T>(path, token, options?)` from `@/api/client` (existing — same as `useEconomy`/`useReceipts`).
- Produces: `BasketItem { product_id: string; name: string; quantity: number; price: number }`, `useBasket(token: string | null) -> { items: BasketItem[]; loading: boolean; message: string | null; sendInstruction: (instruction: string) => Promise<void> }`.

No automated test — no JS/TS test runner exists anywhere in `x5mobile/` (verified: no jest devDependency, no `*.test.ts*` files in the repo). Verified manually in Task 9.

- [ ] **Step 1: Write `x5mobile/src/hooks/useBasket.ts`**

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

export function useBasket(token: string | null) {
  const [items, setItems] = useState<BasketItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    apiFetch<SuggestedBasketResponse>('/basket/suggested', token)
      .then((data) => setItems(data.items))
      .catch(() => {})
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

  return { items, loading, message, sendInstruction };
}
```

- [ ] **Step 2: Type-check**

```bash
cd x5mobile && npx tsc --noEmit
```

Expected: no new errors introduced by this file (pre-existing errors, if any, are unrelated — compare against a run before this change if unsure).

- [ ] **Step 3: Commit**

```bash
git add x5mobile/src/hooks/useBasket.ts
git commit -m "$(cat <<'EOF'
Add useBasket hook

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NDtuwfEXNASSVZjNZFVoxy
EOF
)"
```

---

### Task 8: Frontend — wire the basket card + assistant input into `savings-view.tsx`

**Files:**
- Modify: `x5mobile/src/components/screens/savings-view.tsx`
- Modify: `x5mobile/src/app/index.tsx`

**Interfaces:**
- Consumes: `useBasket(token)` from Task 7, `BrandColors` from `@/constants/theme` (existing).
- Produces: `SavingsViewProps` gains a new required `token: string` field.

No automated test (same reason as Task 7). Verified manually in Task 9.

- [ ] **Step 1: Add `token` to `SavingsViewProps` and call `useBasket` inside `SavingsView`**

In `x5mobile/src/components/screens/savings-view.tsx`, change the imports at the top:

```typescript
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BrandColors } from '@/constants/theme';
import { LeaderboardEntry, Savings, Task } from '@/mock-data';
```

to:

```typescript
import { useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BrandColors } from '@/constants/theme';
import { BasketItem, useBasket } from '@/hooks/useBasket';
import { LeaderboardEntry, Savings, Task } from '@/mock-data';
```

Change the props interface:

```typescript
interface SavingsViewProps {
  tasks: Task[];
  leaderboard: LeaderboardEntry[];
  savings: Savings;
  goHome: () => void;
  goHistory: () => void;
}
```

to:

```typescript
interface SavingsViewProps {
  tasks: Task[];
  leaderboard: LeaderboardEntry[];
  savings: Savings;
  token: string;
  goHome: () => void;
  goHistory: () => void;
}
```

Change the function signature:

```typescript
export function SavingsView({ tasks, leaderboard, savings, goHome, goHistory }: SavingsViewProps) {
  const insets = useSafeAreaInsets();
```

to:

```typescript
export function SavingsView({ tasks, leaderboard, savings, token, goHome, goHistory }: SavingsViewProps) {
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

- [ ] **Step 2: Add the "Корзина на неделю" card, right after the Savings card and before the "Задания" section**

Find this block:

```typescript
        {/* Tasks */}
        <Text style={styles.sectionTitle}>Задания</Text>
```

and insert the new card immediately before it:

```typescript
        {/* Weekly basket */}
        <Text style={styles.sectionTitle}>Корзина на неделю</Text>
        <View style={styles.basketCard}>
          {basketLoading && basketItems.length === 0 ? (
            <ActivityIndicator color={BrandColors.textSecondary} />
          ) : basketItems.length === 0 ? (
            <Text style={styles.basketEmptyText}>Пока нечего предложить — мало истории покупок</Text>
          ) : (
            basketItems.map((item: BasketItem) => (
              <View key={item.product_id} style={styles.basketRow}>
                <Text style={styles.basketItemName}>{item.name}</Text>
                <Text style={styles.basketItemQty}>{item.quantity} шт</Text>
              </View>
            ))
          )}
          {basketMessage && <Text style={styles.basketMessage}>{basketMessage}</Text>}
          <View style={styles.basketInputRow}>
            <TextInput
              style={styles.basketInput}
              placeholder="Например: добавь молоко"
              placeholderTextColor={BrandColors.textSecondary}
              value={instructionText}
              onChangeText={setInstructionText}
              editable={!basketLoading}
            />
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

        {/* Tasks */}
        <Text style={styles.sectionTitle}>Задания</Text>
```

- [ ] **Step 3: Add the new styles**

Find the closing of `styles = StyleSheet.create({ ... })` — locate the `tasksList: { gap: 12 },` entry and add these new style keys right after it:

```typescript
  tasksList: {
    gap: 12,
  },
  basketCard: {
    backgroundColor: BrandColors.cardBg,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: BrandColors.cardBorder,
    padding: 14,
    gap: 10,
  },
  basketRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 4,
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
  basketEmptyText: {
    fontSize: 13,
    color: BrandColors.textSecondary,
  },
  basketMessage: {
    fontSize: 12.5,
    color: BrandColors.textSecondary,
    fontStyle: 'italic',
  },
  basketInputRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 4,
  },
  basketInput: {
    flex: 1,
    backgroundColor: BrandColors.elementBg,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 14,
    color: BrandColors.textPrimary,
  },
  basketSendBtn: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: BrandColors.dark,
    alignItems: 'center',
    justifyContent: 'center',
  },
  basketSendBtnText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
  },
```

- [ ] **Step 4: Pass `token` into `<SavingsView />` from `index.tsx`**

In `x5mobile/src/app/index.tsx`, find:

```typescript
        {screen === 'savings' && (
          <SavingsView
            tasks={data.tasks}
            leaderboard={data.leaderboard}
            savings={{ paid: totalPaid, withoutDiscount: totalPaid + totalSaved }}
            goHome={() => navigate('home')}
            goHistory={() => navigate('history')}
          />
        )}
```

and change it to:

```typescript
        {screen === 'savings' && (
          <SavingsView
            tasks={data.tasks}
            leaderboard={data.leaderboard}
            savings={{ paid: totalPaid, withoutDiscount: totalPaid + totalSaved }}
            token={token}
            goHome={() => navigate('home')}
            goHistory={() => navigate('history')}
          />
        )}
```

(`token` is already in scope inside `AppContent({ token }: { token: string })` — no new prop needed on `AppContent` itself.)

- [ ] **Step 5: Type-check**

```bash
cd x5mobile && npx tsc --noEmit
```

Expected: no new errors.

- [ ] **Step 6: Commit**

```bash
git add x5mobile/src/components/screens/savings-view.tsx x5mobile/src/app/index.tsx
git commit -m "$(cat <<'EOF'
Add weekly basket card + assistant input to the savings screen

Embeds the basket assistant into the existing economy screen instead
of a new screen/mechanic — see the constitution.md conflict note in
docs/superpowers/specs/2026-09-04-basket-ai-assistant-design.md.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NDtuwfEXNASSVZjNZFVoxy
EOF
)"
```

---

### Task 9: Manual end-to-end verification

**Files:** none.

- [ ] **Step 1: Start the backend**

```bash
docker compose up -d db
cd web && poetry run uvicorn webx5.main:app --reload
```

(Or however the project's README documents running it locally — this task assumes Task 2's seed has already been run against this same database.)

- [ ] **Step 2: Start the Expo app**

```bash
cd x5mobile && npx expo start --web
```

- [ ] **Step 3: Log in as a seeded demo user**

Use one of the `phone=...` values Task 2 printed. Confirm login succeeds and lands on the home screen.

- [ ] **Step 4: Open the savings/economy screen**

Confirm the new "Корзина на неделю" card appears below the savings summary, either showing a non-empty product list or the "мало истории покупок" empty state — not stuck on the loading spinner and not crashed.

- [ ] **Step 5: Send a real assistant instruction**

Type something like "добавь молоко" (or another product name visible in `data/v2/unique_products.json` / the catalog) into the input and send it. Confirm:
- The basket list updates to reflect the change (or, if the model didn't understand, a message appears and the list stays the same — not a crash, not a stuck spinner).
- This is a REAL OpenRouter call (not mocked) — confirm by also checking the backend logs show a `basket_assistant.*` structlog line only on the failure paths (a successful call logs nothing extra by design, per Task 5's code — absence of a warning/info line alongside a visibly updated basket is itself the success signal).

- [ ] **Step 6: Try an unrecognizable instruction**

Type something nonsensical (e.g. "asdkjhaskjdh"). Confirm the basket list is unchanged and a message like "Не поняла запрос, попробуй иначе" is shown, not a crash.

- [ ] **Step 7: No commit** — this task verifies, it doesn't change files. If any step failed, go back to the relevant task, fix, and re-run this task from Step 1.
