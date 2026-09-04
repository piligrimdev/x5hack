# Research: Dual-Consumer Authorization

**Date**: 2026-09-03 | **Feature**: [spec.md](spec.md)

## Decision 1: JWT-библиотека

**Decision**: `PyJWT` (пакет `PyJWT>=2.8`)

**Rationale**: Минимальная зависимость без транзитивных пакетов; официально рекомендована в документации FastAPI; поддерживает HS256 (симметричный ключ — достаточно для stateless PoC). Не требует отдельного `cryptography` для HS256.

**Alternatives considered**:
- `python-jose[cryptography]` — тяжелее, требует `cryptography`; было популярно в старых примерах FastAPI, но FastAPI Docs теперь рекомендует PyJWT
- `authlib` — полный OAuth/OIDC стек; избыточен для PoC без сторонних провайдеров

**Usage pattern**:
```python
import jwt  # PyJWT

# Encode
token = jwt.encode({"sub": str(user_id), "exp": ...}, SECRET_KEY, algorithm="HS256")

# Decode (raises jwt.ExpiredSignatureError, jwt.InvalidTokenError on failure)
payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
```

**Config**: `JWT_SECRET_KEY` и `JWT_TTL_DAYS=7` — через env var / pydantic-settings.

---

## Decision 2: Нормализация номера телефона

**Decision**: библиотека `phonenumbers` (порт Google libphonenumber)

**Rationale**: Единственный надёжный способ нормализовать произвольные форматы российских номеров к E.164. Покрывает: `8 (495) 123-45-67`, `+7 916 123 45 67`, `79161234567`, `8916-123-45-67` и т.д. Regex-подход неизбежно пропускает edge-кейсы.

**Alternatives considered**:
- Regex `^(\+7|7|8)\d{10}$` + замена — хрупко; не обрабатывает пробелы, скобки, дефисы в произвольных местах
- Без нормализации — нарушает FR-002 и FR-003; один пользователь мог бы зарегистрироваться дважды с разными форматами

**Usage pattern**:
```python
import phonenumbers

def normalize_phone(raw: str) -> str:
    parsed = phonenumbers.parse(raw, "RU")
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("Invalid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    # → "+79161234567"
```

**Validation**: `phonenumbers.is_valid_number()` отклоняет несуществующие коды (вернёт False) → маппируется в 422 на уровне Pydantic-валидатора или сервиса.

---

## Decision 3: Статичный токен кассы — FastAPI-паттерн

**Decision**: FastAPI `Header` dependency + сравнение с env var

**Rationale**: Простейший и самый тестируемый паттерн. Зависимость вынесена в `dependencies/auth.py` — изолирована от роутов; в тестах легко мокается.

**Alternatives considered**:
- Middleware — сложнее тестировать, нельзя применить выборочно к кассовым роутам
- API Key через query param — небезопасно (логируется в URL)

**Usage pattern**:
```python
from fastapi import Header, HTTPException, Security
import os

def verify_terminal_token(x_terminal_token: str = Header(...)) -> None:
    expected = os.environ["TERMINAL_TOKEN"]
    if x_terminal_token != expected:
        raise HTTPException(status_code=401, detail="Invalid terminal token")
```

`TerminalTokenDep = Annotated[None, Depends(verify_terminal_token)]`

---

## Decision 4: Конфигурация секретов

**Decision**: Переменные окружения, читаемые через `os.environ` в `core/` при сборке

**Rationale**: Соответствует уже принятому паттерну (`core/db.py` читает `DATABASE_URL` напрямую). Для PoC pydantic-settings избыточен.

**New env vars**:
| Var | Example | Description |
|-----|---------|-------------|
| `JWT_SECRET_KEY` | `supersecret` | HS256-ключ; обязателен |
| `JWT_TTL_DAYS` | `7` | TTL access token; default 7 |
| `TERMINAL_TOKEN` | `kassa-secret-token` | Статичный токен кассы; обязателен |

---

## Constitution Re-check Post-Design

- **Privacy (V)**: `User.phone` — в БД только нормализованный номер. В JWT `sub` = UUID пользователя, не номер. Ни один публичный ответ API не возвращает `phone`. Принцип соблюдён.
- **RSI**: `UserRepository` (crud) ← `AuthService` (services) ← `auth_router` (routes). DI через аргументы. Соблюдено.
- **Инициализация**: `encode_jwt`, `normalize_phone` — чистые функции без side effects на импорте. Соблюдено.
