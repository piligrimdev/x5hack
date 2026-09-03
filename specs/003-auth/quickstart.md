# Quickstart Validation Guide: Dual-Consumer Authorization

**Date**: 2026-09-03 | **Spec**: [spec.md](spec.md) | **Contract**: [contracts/auth.md](contracts/auth.md)

## Prerequisites

1. Docker Desktop запущен
2. Файл `.env` создан из `.env.example` (в корне репозитория)
3. В `.env` добавлены новые переменные:
   ```
   JWT_SECRET_KEY=dev-secret-key-change-in-prod
   JWT_TTL_DAYS=7
   TERMINAL_TOKEN=test-terminal-token
   ```

## Setup

```bash
# Из корня репозитория
docker compose up --build -d
# Дождаться: "Application startup complete"
```

---

## Validation Scenarios

### S1: Регистрация нового пользователя (FR-001, FR-002, FR-004, SC-001)

```bash
curl -s -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"phone": "8 (916) 123-45-67"}'
```

**Ожидаемый результат**: 200 + `{"access_token": "<jwt>"}`. Сохрани токен в переменную `$TOKEN`.

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"phone": "8 (916) 123-45-67"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

---

### S2: Дубликат регистрации → 409 (FR-003, SC-002)

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"phone": "+79161234567"}'
# Ожидается: 409
```

Тот же номер в другом формате также должен вернуть 409:
```bash
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"phone": "79161234567"}'
# Ожидается: 409 (нормализован к тому же E.164)
```

---

### S3: Невалидный номер → 422 (FR-008)

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"phone": "123"}'
# Ожидается: 422
```

---

### S4: Повторный вход → новый токен (FR-004, User Story 2)

```bash
curl -s -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"phone": "+79161234567"}'
# Ожидается: 200 + access_token
```

---

### S5: Вход с незарегистрированным номером → 404 (FR-009)

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/login \
  -H "Content-Type: application/json" \
  -d '{"phone": "+79990000000"}'
# Ожидается: 404
```

---

### S6: Защищённый эндпоинт с токеном и без (FR-005, SC-003)

```bash
# Без токена → 401
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/me
# Ожидается: 401

# С токеном → 200
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/me
# Ожидается: 200 + {"user_id": "<uuid>"}
```

---

### S7: Кассовый эндпоинт с валидным токеном (FR-006, SC-005)

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -H "X-Terminal-Token: test-terminal-token" \
  http://localhost:8000/terminal/ping
# Ожидается: 200
```

---

### S8: Изоляция потребителей — JWT пользователя на кассовом эндпоинте (FR-007, SC-004)

```bash
# JWT пользователя на кассовом эндпоинте → 401 (X-Terminal-Token отсутствует)
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/terminal/ping
# Ожидается: 401

# Токен кассы на пользовательском эндпоинте → 401 (Bearer отсутствует)
curl -s -o /dev/null -w "%{http_code}" \
  -H "X-Terminal-Token: test-terminal-token" \
  http://localhost:8000/me
# Ожидается: 401
```

---

### S9: Нормализация — 5 форматов (SC-006)

Зарегистрировать одного пользователя, затем попытаться войти через каждый из форматов. Все должны распознать один и тот же аккаунт:

```bash
# Предполагается, что "+79001112233" зарегистрирован
for phone in "+79001112233" "79001112233" "89001112233" "8 (900) 111-22-33" "+7 900 111-22-33"; do
  result=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/login \
    -H "Content-Type: application/json" \
    -d "{\"phone\": \"$phone\"}")
  echo "$phone → $result"
done
# Ожидается: все форматы → 200
```

---

## Definition of Done

Все 9 сценариев прошли → фича считается реализованной согласно спецификации.
