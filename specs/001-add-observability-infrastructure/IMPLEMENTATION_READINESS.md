# Анализ Готовности к Реализации: Инфраструктура Наблюдаемости

**Дата**: 2026-09-05  
**Анализ**: Текущее состояние codebase webx5 для интеграции инфраструктуры observability

## Исполнительное Резюме

✅ **ГОТОВО К ИНТЕГРАЦИИ** — Сервис webx5 хорошо структурирован и готов к приему instrumentation observability с минимальными изменениями существующего кода.

**Зелёные Флаги**:
- ✅ Structlog уже настроен с JSON output для production
- ✅ Архитектура FastAPI поддерживает injection middleware для метрик
- ✅ Celery уже интегрирован с Redis broker и Beat scheduler
- ✅ OpenRouter API вызовы изолированы в одном модуле (`core/llm.py`)
- ✅ Docker Compose уже на месте с несколькими сервисами
- ✅ Установлены паттерны конфигурации по названию сервиса и переменным окружения

**Жёлтые Флаги** (не блокирующие, обработаны при реализации):
- ⚠️ Нет endpoint метрик Prometheus (требует зависимость `prometheus-client`)
- ⚠️ Langfuse SDK не интегрирован (требует обёртку вокруг `call_openrouter_tools`)
- ⚠️ Flower не работает (требует сервис в docker-compose)
- ⚠️ Логи только записываются в stdout/файлы, не собираются Promtail (требует volume setup контейнера)

---

## Анализ Текущего Состояния

### 1. Структурированное Логирование ✅

**Статус**: Готово

**Текущая Реализация**:
```python
# web/src/webx5/core/logging_config.py
# - Настраивает structlog с поддержкой contextvars
# - JSON renderer для production, ConsoleRenderer для dev
# - Добавляет имя логгера, уровень лога и ISO временную метку ко всем логам
# - root_logger слушает все модули через stdlib integration
```

**Готовность**: Structlog правильно настроен. Все сервисы (web, worker, beat) будут автоматически отправлять структурированные логи в stdout через `logging.StreamHandler`. Promtail может собирать эти логи из stdout контейнера.

**Требуемое Действие**: Нет — существующая конфигурация совместима с Loki.

---

### 2. Приложение FastAPI ✅

**Статус**: Готово к instrumentation

**Текущая Архитектура**:
- FastAPI app определен в `core/server.py`
- Паттерн Router: auth, basket, catalog, challenges, discounts, health, points, receipts, stores
- CORS middleware уже на месте
- Pagination и Scalar API docs включены

**Готовность**: Точка injection middleware FastAPI существует; добавление Prometheus метрик middleware не требует архитектурных изменений.

**Требуемое Действие**: Добавить PrometheusMiddleware для захвата latency запросов и status кодов по endpoint.

---

### 3. Очередь Задач Celery ✅

**Статус**: Готово

**Текущая Конфигурация** (`core/celery_app.py`):
- Redis broker: `redis://redis:6379/0`
- Task модули: `webx5.tasks.{receipt, generation, expiration, basket}`
- Beat schedule: `expire_tasks` запускается каждые 60 секунд
- Конфигурация Worker в docker-compose: 4 concurrent workers на очередях `receipts,challenges`

**Готовность**: Celery полностью настроен и доступен. Flower может подключиться к тому же Redis broker для мониторинга задач.

**Требуемое Действие**: Добавить сервис Flower в docker-compose, указав тот же Redis URL.

---

### 4. Интеграция OpenRouter LLM ✅

**Статус**: Готово к instrumentation

**Текущая Реализация** (`core/llm.py`):
- Функция `call_openrouter_tools()` обрабатывает все OpenRouter API вызовы
- Реализует retry логику с exponential backoff
- Возвращает распарсированные tool calls или выбрасывает исключения
- API ключ из переменной окружения `OPENROUTER_API_KEY`

**Готовность**: Одна точка входа делает тривиальным обёртку в Langfuse SDK instrumentation.

**Требуемое Действие**: 
1. Добавить инициализацию Langfuse SDK в `logging_config.py` или `main.py`
2. Обернуть `call_openrouter_tools()` с контекстом трейса Langfuse
3. Передать user_id в метаданные трейса

---

### 5. Оркестрация Docker Compose ✅

**Статус**: Частично готово

**Текущие Сервисы**:
- `db`: PostgreSQL 16
- `redis`: Redis 7
- `web`: FastAPI приложение (port 8000)
- `worker`: Celery worker (4 concurrency, 2 очереди)
- `beat`: Celery Beat scheduler

**Готовность**: Фундамент прочный. Сервисы мониторинг стека могут быть добавлены без модификации существующих сервисов.

**Требуемое Действие**: Добавить сервисы:
- `prometheus`: Скрейпит `/metrics` endpoint из web сервиса
- `loki`: Получает логи от Promtail
- `promtail`: Собирает логи из контейнеров
- `grafana`: Запрашивает Prometheus и Loki
- `flower`: Мониторит Celery задачи (port 5555)
- `langfuse` (опционально self-hosted): Получает LLM трейсы

---

### 6. Конфигурация Окружения ✅

**Статус**: Готово

**Текущий Паттерн**:
- `.env` файл с defaults
- Переменные окружения: `DATABASE_URL`, `REDIS_URL`, `OPENROUTER_API_KEY`, `SERVICE_NAME`, `LOG_LEVEL`
- Per-service `SERVICE_NAME` в docker-compose (webx5, webx5-worker, webx5-beat)

**Готовность**: Легко может добавить: `LANGFUSE_API_KEY`, `PROMETHEUS_MULTIPROC_DIR`, `LOKI_URL`, `GRAFANA_PASSWORD`.

**Требуемое Действие**: Документировать новые переменные окружения в `.env.example`.

---

## Зависимости для Добавления

| Пакет | Версия | Назначение |
|-------|--------|-----------|
| `prometheus-client` | >=0.19.0,<1.0.0 | Метрики Prometheus в FastAPI |
| `langfuse` | >=2.0.0,<3.0.0 | LLM SDK для сбора трейсов |
| `flower` | >=2.0.0,<3.0.0 | UI мониторинга задач Celery |

**Примечание**: `flower` может также быть установлен как command-line tool в docker образе вместо Python зависимости.

---

## Точки Интеграции

### Structlog → Loki
- **Как**: Promtail скрейпит логи контейнера (stdout) и пушит в Loki
- **Конфиг**: Volume mount Promtail конфига в docker-compose
- **Влияние**: Нет изменений кода; формат логов уже совместим

### Метрики FastAPI → Prometheus
- **Как**: Добавить `PrometheusMiddleware` в app; expose `/metrics` endpoint
- **Файл для модификации**: `web/src/webx5/core/server.py`
- **Влияние**: Минимальное; только injection middleware

### OpenRouter Вызовы → Langfuse
- **Как**: Обернуть `call_openrouter_tools()` с Langfuse trace SDK
- **Файл для модификации**: `web/src/webx5/core/llm.py`
- **Влияние**: Добавить инициализацию Langfuse, обернуть функцию, передать контекст user_id

### Задачи Celery → Flower
- **Как**: Flower подключается к тому же Redis broker как Celery
- **Файл для модификации**: только docker-compose.yml
- **Влияние**: Новый сервис; нет изменений кода

---

## Оценка Рисков

**Низкий Риск**:
- Добавление Promtail collector (внешний инструмент, нет изменений кода приложения)
- Добавление Flower UI (читает Redis события, нет изменений кода приложения)
- Добавление Prometheus middleware (стандартная интеграция библиотеки)

**Средний Риск**:
- Интеграция Langfuse SDK (требует обёртки существующей функции; нужно сохранить обратную совместимость)
  - **Митигация**: Если Langfuse недоступен, функция ведёт себя нормально (SDK обрабатывает gracefully)

**Нет Риска**:
- Конфигурация базы данных или Celery (только добавление мониторинга, не изменение существующего setup)

---

## Рекомендуемая Последовательность

1. **Фаза 1 - Логирование + Метрики**: Добавить Promtail, Loki, Grafana в docker-compose; добавить Prometheus middleware
2. **Фаза 2 - Мониторинг Celery**: Добавить Flower в docker-compose
3. **Фаза 3 - LLM Observability**: Интегрировать Langfuse SDK вокруг OpenRouter вызовов
4. **Фаза 4 - Дашборды**: Создать дашборды Grafana (обсуждено в `/speckit-clarify`)

---

## Заключение

✅ Codebase webx5 архитектурно звучен для интеграции observability. Все фундаментальные компоненты (structlog, Celery, FastAPI) на месте. Реализация может продолжаться с уверенностью что изменения будут аддитивными и не breaking.
