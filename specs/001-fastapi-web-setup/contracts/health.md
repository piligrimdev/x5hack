# Contract: Health Check Endpoint

**Service**: webx5 API
**Version**: v1

## GET /health

Публичный эндпоинт проверки работоспособности сервиса. Не требует аутентификации.

### Request

```
GET /health HTTP/1.1
```

Параметры, заголовки и тело запроса — не требуются.

### Response: 200 OK

```json
{
  "status": "ok"
}
```

| Поле | Тип | Описание |
|---|---|---|
| `status` | `string` | Всегда `"ok"` при нормальной работе сервиса |

### Response: 5xx

Если сервис не может обработать запрос (паника, неинициализированное приложение), клиент получает стандартный HTTP 500 или connection refused. Поле `status` в этом случае не гарантируется.

### Performance SLA

- p50 < 50 мс
- p99 < 500 мс

### Usage

```bash
# Проверка живости сервиса
curl -s http://localhost:8000/health

# Ожидаемый вывод
{"status":"ok"}
```
