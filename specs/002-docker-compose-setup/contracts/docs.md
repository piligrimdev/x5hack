# Contract: API Documentation Endpoint

**Service**: webx5 API
**Version**: v1

## GET /docs

Интерактивная документация API через Scalar UI. Публичный эндпоинт, аутентификация не требуется.

### Request

```
GET /docs HTTP/1.1
```

Параметры, заголовки и тело — не требуются.

### Response: 200 OK

HTML-страница с интерфейсом Scalar. Content-Type: `text/html`.

Страница содержит:
- Список всех зарегистрированных эндпоинтов сервиса
- Возможность отправить тестовый запрос («Try it») прямо из браузера
- OpenAPI-спецификацию, актуальную на момент запроса

### GET /openapi.json

Машиночитаемая OpenAPI 3.x спецификация в формате JSON. Используется Scalar как источник данных для `/docs`.

```
GET /openapi.json HTTP/1.1
```

**Response**: 200 OK, `application/json`, OpenAPI 3.x schema.

### Disabled endpoints

Стандартные FastAPI-эндпоинты документации (`/docs` Swagger UI, `/redoc`) отключены — заменены Scalar.

### Usage

```bash
# Открыть документацию в браузере
open http://localhost:8000/docs

# Получить OpenAPI-спецификацию
curl -s http://localhost:8000/openapi.json | python3 -m json.tool | head -20
```

### Performance SLA

- Страница `/docs` загружается < 3 секунды (SC-005)
