# Архитектура системы — X5 Loyalty PoC

> Документ описывает текущее состояние (as-is), целевую архитектуру (to-be) и трейд-оффы в рамках PoC/MVP.

---

## As-Is — что реализовано сейчас

### Сервисы

| Сервис               | Технология                                     | Статус         |
| -------------------- | ---------------------------------------------- | -------------- |
| API                  | FastAPI, Python 3.12, sync SQLAlchemy, Alembic | ✅ работает    |
| База данных          | PostgreSQL 16                                  | ✅ работает    |
| Мобильное приложение | React Native, Expo 57, TypeScript              | ✅ скаффолд    |
| Фоновые задачи       | Celery 5.4 (worker + beat)                     | ✅ работает    |
| Кэш / брокер         | Redis 7                                        | ✅ работает    |

**docker-compose:** `db`, `redis`, `web`, `worker`, `beat` (5 сервисов). См. `specs/006-user-challenges/`.

**Celery-задачи (реализованы):**
- `webx5.tasks.receipt.process_receipt` — очередь `receipts`; триггер: POST /receipts enqueue после успешной вставки; ответственность: pessimistic user-lock, инкремент прогресса активных tasks, atomic reward creation, enqueue замены для завершённых.
- `webx5.tasks.generation.generate_challenges` — очередь `challenges`; триггер: process_receipt (для новичка count=3 / для замены count=1) + expire_tasks; ответственность: mix из `spend_threshold`+`category_expansion`+`llm`, persist в `task` + `task_criterion`, аудит в `challenge_generation_log`.
- `webx5.tasks.expiration.expire_tasks` — Beat каждые 60 сек; SELECT FOR UPDATE SKIP LOCKED overdue tasks → status='истекло' → enqueue replacements.

### API (`web/`)

Пакет: `src/webx5/`, структура соответствует правилам (core / crud / services / routes / schemas / entities / dependencies / utils).

**Роуты:**

| Метод | Путь                | Назначение                            |
| ----- | ------------------- | ------------------------------------- |
| GET   | /health             | Healthcheck                           |
| POST  | /register           | Регистрация по номеру телефона        |
| POST  | /login              | Логин по номеру телефона              |
| POST  | /refresh            | Обновление пары токенов               |
| GET   | /me                 | Текущий пользователь (Bearer)         |
| GET   | /terminal/ping      | Пинг для терминала (X-Terminal-Token) |
| POST  | /receipts           | Создание чека кассой (X-Terminal-Token) |
| POST  | /receipts/calculate | Предварительный расчёт скидок          |
| GET   | /receipts           | История чеков пользователя (Bearer)    |
| GET   | /receipts/economy   | Сводка экономии пользователя (Bearer)  |
| GET   | /challenges/current | 3 активных задания пользователя (Bearer) |

**Авторизация:** JWT stateless. Access + refresh — оба возвращаются в теле ответа (не HttpOnly cookie). Refresh принимается в теле запроса (не cookie). Отличается от целевой схемы из правил — см. трейд-оффы.

**Аутентификация терминала (POS):** `X-Terminal-Token` header, статический секрет из env. Отдельный `Depends` (`TerminalTokenDep`).

### База данных

**Реализовано в миграциях:**

- `users` — id (UUID), phone (unique), created_at

**Реализовано (после feature 005 + 006):**

- category, product, discount (+ value_type, link_task_id), discount_type, discount_link_type
- store_format, store, format_discount, store_discount
- segment, loyalty_card
- receipt, receipt_item
- **task**, **task_status**, **task_criterion** (EAV), **task_receipt_increment** (dedupe), **challenge_generation_log** (audit)

**Осталось на бумаге:**

- brand (`products.brand_id` без FK)

### Мобильное приложение (`x5mobile/`)

Expo Router, tab-навигация (Home / Explore). Экран Home отображает **хардкоженные** данные: экономия 2 450 ₽, уровень 5. Никакой интеграции с API нет. Авторизации нет.

---

## To-Be — целевая архитектура PoC

### Общая схема

```
┌─────────────────────────────────────────────────────────┐
│                     Mobile App                          │
│  React Native + Expo 57                                 │
│  - JWT хранится локально (AsyncStorage)                 │
│  - Кэш: аватар, челлендж, рейтинг (TTL-стратегия)      │
│  - Pull при открытии экрана / истечении TTL             │
└────────────────────┬────────────────────────────────────┘
                     │ HTTPS / REST
┌────────────────────▼────────────────────────────────────┐
│                  FastAPI (монолит)                       │
│  - Auth (register / login / refresh)                    │
│  - Mock-эндпоинты: purchases, products, discounts       │
│  - Core API: challenges, avatar, rating, coupons        │
│  - POST /purchases → idempotency key → Celery.delay()   │
└────────┬──────────────────────────┬─────────────────────┘
         │ SQL (sync)               │ task.delay()
┌────────▼────────┐      ┌──────────▼──────────────────── ┐
│   PostgreSQL    │      │         Redis                   │
│                 │      │  - Celery broker                │
│  - users        │      │  - Celery result backend        │
│  - loyalty_card │      │  - API response cache           │
│  - receipt      │      └─────────────┬───────────────────┘
│  - receipt_item │                    │
│  - task         │      ┌─────────────▼───────────────────┐
│  - product      │      │       Celery Worker             │
│  - discount     │      │                                 │
│  - store        │◄─────│  Очереди:                       │
│  - segment      │      │  high: update_economy,          │
│  - coupon       │      │         update_rating           │
│  - avatar_state │      │  low:  generate_challenges,     │
│  - purchase_    │      │         segmentation            │
│    events       │      │                                 │
│  - failed_tasks │      │  Beat: generate_challenges      │
└─────────────────┘      │         _nightly (03:00)        │
                         └─────────────────────────────────┘
                                      │ LLM API
                         ┌────────────▼────────────────────┐
                         │  LLM Provider (Claude / GPT)    │
                         │  - Генерация челленджей         │
                         │  - reasoning field в ответе     │
                         └─────────────────────────────────┘

POS (касса) — MOCK:
  POST /purchases → idempotency key = receipt_id
  Сервер: 201 Created / 409 Conflict
  Retry на стороне клиента, дедупликация по UNIQUE constraint
```

### Что добавляется к инфраструктуре

| Компонент     | Назначение                                       |
| ------------- | ------------------------------------------------ |
| Redis         | Celery broker + result backend + кэш ответов API |
| Celery Worker | Фоновые задачи (4 типа)                          |
| Celery Beat   | Планировщик ночного батча                        |
| Flower (опц.) | Мониторинг задач на демо                         |

docker-compose добавляет: `redis`, `worker`, `beat`.

### Celery-задачи

| Задача                | Очередь | Триггер                                 | Описание                                           |
| --------------------- | ------- | --------------------------------------- | -------------------------------------------------- |
| `update_economy`      | high    | POST /purchases                         | Пересчитывает `savings_total` пользователя по чеку |
| `update_rating`       | high    | POST /purchases                         | Обновляет precalculated рейтинг в geo_cluster      |
| `generate_challenges` | low     | Nightly Beat / при отсутствии активного | LLM-вызов, генерирует задание + reasoning          |
| `segmentation`        | low     | Nightly Beat                            | Пересчитывает segment для пользователей            |

Fallback для `generate_challenges`: при LLM-ошибке → выдаётся шаблонный челлендж из Postgres, пользователь не видит пустой экран.

### Новые API-эндпоинты

| Метод | Путь                | Описание                                             |
| ----- | ------------------- | ---------------------------------------------------- |
| POST  | /purchases          | Приём чека, idempotency по receipt_id                |
| GET   | /me/version         | Лёгкая проверка версии данных (мобилка до full pull) |
| GET   | /avatar             | Аватар пользователя (JSON-параметры)                 |
| GET   | /challenges/current | Текущее задание + reasoning                          |
| GET   | /rating             | Рейтинг в geo_cluster (без ФИО/адресов)              |
| GET   | /coupons            | Активные купоны пользователя                         |
| GET   | /economy            | Сводка экономии                                      |

### Новые сущности БД

| Таблица           | Ключевые поля                                                                     |
| ----------------- | --------------------------------------------------------------------------------- |
| `loyalty_card`    | id, phone, segment_id, savings_total, geo_cluster                                 |
| `avatar_state`    | loyalty_card_id, level, skin, accessory_ids (JSON)                                |
| `receipt`         | id (= idempotency key), loyalty_card_id, store_id, purchase_date                  |
| `receipt_item`    | receipt_id, product_id, quantity, base_price, paid_price, discounted_amount       |
| `task`            | loyalty_card_id, status, criterion_type, criterion_entity_id, deadline, reasoning |
| `coupon`          | loyalty_card_id, code, discount_value, expires_at, used_at                        |
| `purchase_events` | receipt_id, status (pending/done), created_at — outbox для Celery                 |
| `failed_tasks`    | task_name, payload, attempts, last_error — эмуляция DLQ                           |

Все mock-сущности (product, brand, category, discount, store) — seed-данные, не редактируются через API.

### Мобильное приложение — TTL-стратегия кэша

| Данные           | TTL                  | Инвалидация                      |
| ---------------- | -------------------- | -------------------------------- |
| Аватар           | до следующей покупки | при открытии после `/me/version` |
| Текущий челлендж | до конца суток       | при `/me/version`                |
| Рейтинг          | 30–60 мин            | по TTL                           |
| Купоны           | не кэшируются        | всегда свежие                    |

Паттерн: stale-while-revalidate. Сначала показываем кэш, в фоне проверяем `/me/version` — если изменилось, тянем свежие данные.

---

## Трейд-оффы в рамках PoC

### 1. Redis как Celery broker (вместо RabbitMQ)

**Выбор:** Redis.

| Аспект               | Redis              | RabbitMQ   |
| -------------------- | ------------------ | ---------- |
| Количество сервисов  | 1 (broker + cache) | 2          |
| Дурабилити сообщений | Только с AOF/RDB   | Из коробки |
| DLQ                  | Ручная эмуляция    | Нативно    |
| Сложность на демо    | Низкая             | Средняя    |

Для PoC все 4 задачи идемпотентны — потеря сообщения при перезапуске Redis не катастрофична. На хакатоне ценнее один сервис меньше, чем нативный DLQ.

### 2. Sync SQLAlchemy (не async)

**Выбор:** sync.

FastAPI поддерживает async, но SQLAlchemy async требует `asyncpg` и другого стиля сессий. Текущий sync-стек уже рабочий. Для PoC с небольшой нагрузкой throughput не критичен. Переход на async — в BACKLOG.

### 3. JWT refresh в теле ответа (не HttpOnly cookie)

**Выбор:** тело ответа (отход от правил для PoC).

HttpOnly cookie корректна для веб-клиентов, но React Native не имеет браузерного cookie-jar — нужна ручная передача через заголовок. Упрощение: оба токена в теле, мобилка хранит в AsyncStorage. Для продакшна — переработать.

### 4. Outbox без брокера между POS и API

**Выбор:** `purchase_events` таблица + Celery polling.

Альтернатива — Kafka/RabbitMQ между POS и API. Для mock-кассы это over-engineering: POS — скрипт, который делает HTTP POST с retry. Idempotency key (`receipt_id`) + UNIQUE constraint в Postgres = гарантия ровно одной записи. Outbox-таблица даёт историю без второго брокера.

### 5. LLM async через Celery (не sync в хендлере)

**Выбор:** async через Celery, API отвечает 202.

LLM-вызов занимает 2–10 секунд. Sync в хендлере → таймаут на демо. Async → API мгновенно отвечает, мобилка пуллит результат. Усложняет клиентский flow, но критично для UX на демо.

### 6. Монолит (не микросервисы)

**Выбор:** монолит.

Два потребителя (мобилка + mock POS), данные практически идентичны, команда 3 человека. Микросервисы добавляют сложность без выгоды на этом масштабе. Монолит быстрее разрабатывать и проще дебажить во время демо.

### 7. Аватар как JSON в Postgres (не файл/изображение)

**Выбор:** JSON-параметры, рендер на клиенте.

Хранение PNG требует S3/MinIO и усложняет деплой. JSON-параметры (level, skin, accessory_ids) — мобилка рендерит визуал сама по конфигу. Нет файлового хранилища в docker-compose.

---

## Что остаётся в BACKLOG

- Переход на async SQLAlchemy + asyncpg
- HttpOnly cookie для refresh token (веб-версия)
- Нативный DLQ через RabbitMQ при росте нагрузки
- Push-уведомления (FCM/APNs) вместо pull при появлении нового челленджа
- Антифрод-скоринг по `payment_card_uid` (H6 из CONTEXT_PACK)
