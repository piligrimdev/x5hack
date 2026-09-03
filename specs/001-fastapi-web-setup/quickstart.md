# Quickstart & Validation Guide

**Feature**: 001-fastapi-web-setup
**Date**: 2026-09-03

## Prerequisites

- Python 3.12+ установлен
- Poetry установлен (`pip install poetry`)
- PostgreSQL запущен и доступен (или Docker)
- Склонирован репозиторий, рабочая директория — корень проекта

## Setup

### 1. Установить зависимости

```bash
cd web
poetry install
```

### 2. Настроить переменные окружения

Создать `web/.env` (или корневой `.env`):

```env
DATABASE_URL=postgresql+psycopg2://postgres:password@localhost:5432/x5hack
SERVICE_NAME=webx5
```

### 3. Применить миграции

```bash
cd web
poetry run alembic upgrade head
```

**Ожидаемый вывод**: `INFO  [alembic.runtime.migration] Running upgrade  -> <rev_id>, Init`

### 4. Запустить сервис

```bash
cd web
poetry run python -m webx5
```

**Ожидаемый вывод**: structlog-логи запуска с `app.starting` событием и адресом сервера.

## Validation Scenarios

### Scenario 1: Health Check (P1 — базовая проверка)

```bash
curl -s http://localhost:8000/health
```

**Ожидаемый ответ**:
```json
{"status":"ok"}
```

**HTTP статус**: 200

---

### Scenario 2: Health Check Response Time

```bash
curl -o /dev/null -s -w "Total: %{time_total}s\n" http://localhost:8000/health
```

**Ожидаемый вывод**: `Total: 0.0XXs` (менее 0.5 секунды)

---

### Scenario 3: Migrations Applied

```bash
cd web
poetry run alembic current
```

**Ожидаемый вывод**: `<rev_id> (head)` — без `(None)`.

---

### Scenario 4: Неверный DATABASE_URL → понятная ошибка

Установить `DATABASE_URL=postgresql+psycopg2://bad:bad@localhost:9999/x5hack`, запустить сервис.

**Ожидаемый результат**: сервис не стартует, в логах — сообщение об ошибке подключения (не голый stack trace).

---

### Scenario 5: Smoke Test (автоматизированный)

```bash
cd web
poetry run pytest tests/ -v
```

**Ожидаемый результат**: все тесты проходят (зелёный).

## Contract Reference

- [Health endpoint contract](contracts/health.md)
- [Full DB schema](../../context/schema.md)
