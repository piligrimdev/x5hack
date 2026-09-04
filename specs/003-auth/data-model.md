# Data Model: Dual-Consumer Authorization

**Date**: 2026-09-03 | **Feature**: [spec.md](spec.md)

## Entity: User

Зарегистрированный клиент мобильного приложения.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK, NOT NULL, server-generated | Используется как `sub` в JWT |
| `phone` | VARCHAR(20) | UNIQUE, NOT NULL, indexed | E.164 format: `+7XXXXXXXXXX` |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL, DEFAULT now() | Дата регистрации |

**Table name**: `users`

**Uniqueness rule**: уникальность проверяется по `phone` после нормализации к E.164 (FR-002, FR-003).

**Lifecycle**: одно состояние (active). Удаление, блокировка, смена номера — вне скоупа PoC.

**Relationships**: нет в рамках данной фичи; UUID пользователя будет FK в будущих таблицах `purchases`, `challenges` и т.д.

---

## Runtime tokens (не хранятся в БД)

### JWT Access Token

Stateless, не персистируется. Структура payload:

| Claim | Value | Notes |
|-------|-------|-------|
| `sub` | UUID пользователя (str) | Идентификатор; не содержит phone |
| `exp` | now + 7 дней | Unix timestamp |
| `iat` | now | Unix timestamp |

Algorithm: HS256. Ключ: `JWT_SECRET_KEY` из env.

### Terminal Token

Строковый секрет из env var `TERMINAL_TOKEN`. Передаётся в заголовке `X-Terminal-Token`. Не хранится в БД и не имеет структуры payload.

---

## Alembic Migration

Новая ревизия: `add_users_table`

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_users_phone ON users(phone);
```

> `gen_random_uuid()` требует расширение `pgcrypto` (доступно в PostgreSQL 13+ по умолчанию).
> Альтернатива: генерировать UUID на стороне приложения через `uuid.uuid4()` и передавать явно.
