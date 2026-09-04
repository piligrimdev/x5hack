# Data Model: Docker Compose Setup

**Feature**: 002-docker-compose-setup
**Date**: 2026-09-03

## Scope

Данная фича не вводит новых бизнес-сущностей в базу данных. Все таблицы проекта описаны в `context/schema.md` и будут добавлены через отдельные Alembic-миграции в последующих фичах.

## Configuration Entities (runtime, not stored in DB)

| Сущность | Описание | Источник |
|---|---|---|
| Docker Service `db` | PostgreSQL-контейнер с healthcheck | `docker-compose.yml` |
| Docker Service `web` | FastAPI-контейнер, зависит от `db` | `docker-compose.yml` |
| Named Volume `pgdata` | Persistent-хранилище данных PostgreSQL | `docker-compose.yml` |
| Entrypoint Script | Скрипт инициализации: миграции → сервер | `web/entrypoint.sh` |

## Environment Variables (compose-level)

| Переменная | Дефолт | Описание |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://postgres:password@db:5432/x5hack` | DSN для веб-сервиса |
| `POSTGRES_USER` | `postgres` | Пользователь БД |
| `POSTGRES_PASSWORD` | `password` | Пароль БД |
| `POSTGRES_DB` | `x5hack` | Имя базы данных |
| `PORT` | `8000` | Публикуемый порт веб-сервиса |
| `SERVICE_NAME` | `webx5` | Имя сервиса в логах |

## Notes

- `DATABASE_URL` в compose использует hostname `db` (имя сервиса), а не `localhost`.
- `POSTGRES_USER`/`PASSWORD`/`DB` должны быть согласованы между сервисами `db` и `web`.
- Полная схема БД: `context/schema.md`.
