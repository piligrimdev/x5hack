# API Contract: Authorization

**Date**: 2026-09-03 | **Base URL**: `http://localhost:8000`

All request/response bodies: `Content-Type: application/json`.
All error bodies: `{"detail": "<message>"}` (FR-011).

---

## Public Endpoints (no auth required)

### POST /register

Регистрация нового пользователя по номеру телефона.

**Request body**:
```json
{
  "phone": "+79161234567"
}
```
Допустимые форматы `phone`: `+79161234567`, `79161234567`, `89161234567`, `8 (916) 123-45-67`, `+7 916 123-45-67`. Система нормализует к E.164 перед сохранением.

**Response 200 OK**:
```json
{
  "access_token": "<jwt_access>",
  "refresh_token": "<jwt_refresh>"
}
```

**Response 409 Conflict** — номер уже зарегистрирован:
```json
{
  "detail": "Phone already registered"
}
```

**Response 422 Unprocessable Entity** — невалидный формат номера:
```json
{
  "detail": [{ "loc": ["body", "phone"], "msg": "Invalid phone number", "type": "value_error" }]
}
```

---

### POST /login

Вход существующего пользователя по номеру телефона.

**Request body**:
```json
{
  "phone": "+79161234567"
}
```

**Response 200 OK**:
```json
{
  "access_token": "<jwt_access>",
  "refresh_token": "<jwt_refresh>"
}
```

**Response 404 Not Found** — номер не зарегистрирован:
```json
{
  "detail": "User not found"
}
```

**Response 422 Unprocessable Entity** — невалидный формат номера:
```json
{
  "detail": [{ "loc": ["body", "phone"], "msg": "Invalid phone number", "type": "value_error" }]
}
```

---

---

### POST /refresh

Обмен refresh token на новую пару access + refresh.

**Request body**:
```json
{
  "refresh_token": "<jwt_refresh>"
}
```

**Response 200 OK**:
```json
{
  "access_token": "<new_jwt_access>",
  "refresh_token": "<new_jwt_refresh>"
}
```

**Response 401 Unauthorized** — просроченный или невалидный refresh token (или передан access token вместо refresh):
```json
{
  "detail": "Could not validate credentials"
}
```

---

## Mobile User Protected Endpoints

Все запросы требуют заголовок:
```
Authorization: Bearer <access_token>
```

**Response 401 Unauthorized** при отсутствии или невалидном токене:
```json
{
  "detail": "Could not validate credentials"
}
```

Пример защищённого роута (шаблон для будущих фич):
```
GET /me → { "user_id": "<uuid>" }
```

---

## Terminal (POS) Protected Endpoints

Все запросы требуют заголовок:
```
X-Terminal-Token: <static_terminal_token>
```

**Response 401 Unauthorized** при отсутствии или невалидном токене:
```json
{
  "detail": "Invalid terminal token"
}
```

**Response 403 Forbidden** при попытке использовать JWT пользователя вместо токена кассы:
> Достигается автоматически: JWT пользователя передаётся через `Authorization: Bearer`, а `X-Terminal-Token` при этом отсутствует → 401.
> Если же передать JWT в `X-Terminal-Token` — он не совпадёт со статичным токеном → 401.
> 403 явно возвращается, если пользовательский JWT используется как `X-Terminal-Token` (проверяется отдельным Depends).

Шаблон кассового эндпоинта (будущие фичи):
```
POST /terminal/purchase  → 200
GET  /terminal/loyalty   → 200
```

---

## Cross-Consumer Isolation Matrix

| Токен \ Эндпоинт | /register /login | User-protected | Terminal-protected |
|-----------------|-----------------|---------------|-------------------|
| Нет токена | ✅ OK | 401 | 401 |
| Валидный JWT пользователя | ✅ OK | ✅ OK | 401 |
| Невалидный JWT | ✅ OK | 401 | 401 |
| Валидный X-Terminal-Token | ✅ OK | 401 (нет Bearer) | ✅ OK |
| Невалидный X-Terminal-Token | ✅ OK | 401 | 401 |
