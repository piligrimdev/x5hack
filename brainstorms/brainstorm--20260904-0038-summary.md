# Summary: Архитектура системы (X5 hackathon)
Date: 2026-09-04 | Ideas: 17 | Forks: 0

## Key Themes
- Упрощение инфраструктуры: Redis вместо RabbitMQ, монолит вместо микросервисов
- Надёжность через идемпотентность: receipt_id + 409, outbox без брокера
- Async-first для LLM: тяжёлые вызовы через Celery, API не блокируется
- Клиентский кэш вместо push: мобилка сама управляет свежестью
- Объяснимость ИИ встроена в API (reasoning field)

## Confirmed Decisions
- POS = mock; лояльность/товары/скидки = mock; фокус на challenge/rating/economy/avatar/coupon
- Celery нужен: retry, history, тяжёлые LLM-вызовы
- Long polling убран: кэш на мобилке + pull по необходимости
- RabbitMQ исключён

## All Ideas

### Инфраструктура
1. Redis как Celery broker вместо RabbitMQ (один сервис: broker + cache)
2. Две очереди Celery: high_priority (update_economy, update_rating) + low_priority (generate_challenges, segmentation)
3. Celery Beat: одна ночная джоба `generate_challenges_nightly`; остальное — event-driven через .delay()
4. Эмуляция DLQ: таблица `failed_tasks` в Postgres + Celery Beat retry джоб

### Надёжность / POS
5. Idempotency key (receipt_id) на POST /purchases → 201 или 409 + retry на стороне кассы
6. Outbox-паттерн без брокера: таблица `purchase_events` → Celery worker сканирует pending

### Данные / Postgres
7. Materialized view / precalculated поле `savings_total` для рейтинга, индекс сверху
8. Аватар = JSON-параметры в Postgres (level, skin, accessory_ids); рендер на клиенте
9. Сегмент юзера = enum-поле в `users`, пересчитывается Celery раз в сутки
10. Купоны = записи в Postgres с `expires_at` / `used_at`; батч-генерация Celery заранее

### LLM / Celery tasks
11. LLM-вызов всегда async через Celery → API отвечает 202 сразу
12. Fallback при LLM-ошибке: шаблонный челлендж из Postgres (не пустой экран)
13. Поле `reasoning` в `/challenges/current` — объяснение почему этот челлендж (UX + hit rate)

### Мобилка
14. Stale-while-revalidate: показываем кэш сразу → фоновый refresh
15. TTL-стратегия: аватар — до следующей покупки; челлендж — до конца дня; рейтинг — 30–60 мин
16. Купоны не кэшируются — всегда свежие (валидность критична)
17. HEAD /me/version endpoint — мобилка проверяет изменения перед full pull

Full session: brainstorm--20260904-0038.md
