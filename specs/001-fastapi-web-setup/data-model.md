# Data Model: FastAPI Web Application Setup

**Feature**: 001-fastapi-web-setup
**Date**: 2026-09-03

## Scope

Данная фича устанавливает инфраструктуру доступа к данным. Новых бизнес-сущностей не вводит — таблицы будут добавлены в последующих фичах на основе `context/schema.md`.

## SQLAlchemy Base

Единственная сущность данного этапа — DeclarativeBase, от которой наследуются все будущие модели.

```
Base
  └── (future entities from context/schema.md)
```

## Database Connection

| Параметр | Значение |
|---|---|
| Переменная окружения | `DATABASE_URL` |
| Формат | `postgresql+psycopg2://user:pass@host:5432/dbname` |
| Pool | `pool_pre_ping=True` (проверка соединения перед использованием) |
| Session mode | Sync (sqlalchemy Session, не AsyncSession) |

## Alembic Migration State

После применения базовой миграции в БД создаётся только таблица `alembic_version` (служебная). Бизнес-таблицы добавляются в последующих фичах через отдельные ревизии.

## Full Schema Reference

Полная схема БД со всеми сущностями проекта описана в `context/schema.md`. При реализации entities/ строго следовать этой схеме.
