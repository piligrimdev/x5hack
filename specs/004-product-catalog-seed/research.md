# Research: Product Catalog and Seed Script

**Branch**: `004-product-catalog-seed` | **Date**: 2026-09-04

---

## Decision 1: Pagination Library

**Decision**: `fastapi-pagination` с расширением `[sqlalchemy]`

**Rationale**: Самая популярная библиотека пагинации для FastAPI-экосистемы. Предоставляет:
- `Page[T]` — готовая Pydantic-схема ответа со списком + метаданными (total, page, size, pages)
- `paginate(query, params)` — оборачивает SQLAlchemy-запрос, не требует дублирования логики в каждом роуте
- `add_pagination(app)` — одна строка в `server.py`, после чего все роуты с `Page[T]` автоматически получают query-params `page` и `size`
- `Params` как `Annotated[Params, Depends()]` — переиспользуемая зависимость

**Установка**: `fastapi-pagination[sqlalchemy]` добавляется в `web/pyproject.toml` через Poetry.

**Дефолтные query-params**: `?page=1&size=50` (настраивается через `CustomPage` с `max_size`).

**Alternatives considered**:
- Custom `Depends(offset_limit)` — больше кода, не переиспользуется без явного дублирования
- `fastapi-paginate` — значительно меньше adoption, хуже документация

---

## Decision 2: Аутентификация для read vs write эндпоинтов

**Decision**:
- **GET** (каталог): `CurrentUserUUID` — JWT Bearer, обязателен для любого клиента
- **POST / PUT / DELETE** (управление каталогом): `TerminalTokenDep` — заголовок `X-Terminal-Token`, только кассовый аппарат

**Rationale**: `TerminalTokenDep` уже реализован в `dependencies/auth.py` и используется в `/terminal/ping`. Это готовый механизм идентификации кассового аппарата без ролей. Мобильный клиент всегда имеет JWT — читающие эндпоинты единообразно используют один auth-механизм. Кассовый аппарат для чтения каталога в PoC-демо также регистрируется как пользователь и получает JWT.

**Alternatives considered**:
- Read endpoints public (без auth) — проще для кассы, но противоречит спеку (JWT required)
- Read endpoints принимают ОБА механизма — усложняет middleware, не нужно для PoC

---

## Decision 3: UPSERT при импорте (seed script)

**Decision**: SQLAlchemy PostgreSQL-native UPSERT через `insert().on_conflict_do_update(index_elements=['sku_id'], set_={...})`

**Rationale**: Атомарная операция на уровне БД; нет гонки между SELECT и INSERT; работает корректно при параллельных запусках. SQLAlchemy 2.x (`sqlalchemy.dialects.postgresql.insert`) поддерживает нативно.

**Alternatives considered**:
- SELECT + INSERT/UPDATE в Python — требует явного управления транзакцией, медленнее для больших файлов
- `session.merge()` — может вызывать лишние SELECT; не даёт контроля над тем, какие поля обновляются

---

## Decision 4: Расположение seed-скрипта

**Decision**: `web/scripts/seed_products.py` — отдельная директория `scripts/` на уровне `web/`, вне пакета `webx5/`.

**Rationale**: Скрипты по правилам проекта не смешиваются с API-кодом. Директория `web/scripts/` логична: скрипт импортирует из `webx5.*` (через `PYTHONPATH=web/src`), но сам не является частью пакета. Конфигурация — через `SEED_FILE_PATH` в `.env` (существующий python-dotenv).

**Alternatives considered**:
- `web/src/webx5/scripts/` — создаёт лишнее связывание скрипта с пакетом; скрипт стал бы частью модуля
- Корень репозитория — нет, скрипт относится к web-сервису

---

## Decision 5: brand_id для импортированных товаров

**Decision**: `brand_id` — nullable (NULL) для товаров, загруженных из JSONL. Placeholder-бренд не создаётся.

**Rationale**: Исходные данные не содержат информации о бренде. Null — правильный семантический сигнал «бренд неизвестен». Создание фиктивной записи «Unknown brand» засоряет справочник и усложняет будущую работу с брендами.

**Alternatives considered**: Auto-create "Unknown" — отклонено (семантический мусор).

---

## Decision 6: Поле sku_id в сущности Product

**Decision**: Добавить поле `sku_id: str` (unique, indexed, not null) в SQLAlchemy entity `Product` и создать Alembic-миграцию.

**Rationale**: `sku_id` — внешний идентификатор из системы поставщика/кассы (например, `sku_0042`). Отсутствует в текущей `context/schema.md` — это расширение схемы. Индекс необходим для быстрого lookup кассой.

---

## Decision 7: Структура response для Product

**Decision**: `ProductResponse` включает `category` как вложенный объект `CategoryResponse` (не только `category_id`).

**Rationale**: User Story 2 (касса) требует «карточку товара: id, название, текущая цена, **категория**». Для UX мобильного клиента не нужен дополнительный запрос к `/categories/{id}` для показа названия категории.

**Alternatives considered**: Возвращать только `category_id` — требует дополнительного запроса на клиенте.
