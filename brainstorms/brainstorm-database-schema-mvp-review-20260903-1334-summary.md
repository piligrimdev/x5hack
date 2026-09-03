# Summary: Database Schema MVP Review — X5 Loyalty
Date: 2026-09-03 | Ideas: 11 | Forks: 0

## Key Themes
- Снимок данных на момент покупки — история неизменяема даже при изменении цен/скидок
- Скидки: scope + valid_from/to + best-price-wins в бизнес-логике
- Задания с одним структурированным критерием (criterion_type / entity_id / quantity)
- Магазин как носитель geo_cluster — анонимный район без адреса пользователя
- Чёткая граница PoC vs Backlog

## All Ideas
1. best-price-wins — скидки не стекаются, бизнес-логика выбирает минимальную цену
2. Три ценовых поля в позиции чека: base_price_at_purchase / paid_price / discounted_amount
3. scope на скидке: all / by_format / by_store
4. valid_from / valid_to на скидке (NULL = бессрочно, московский timezone)
5. format_discount + store_discount M2M таблицы
6. Магазин с geo_cluster — район пользователя через транзакцию, не через адрес
7. channel (online/offline) в чеке
8. Задание: criterion_type + entity_id + quantity_target + quantity_current
9. task_status — отдельная справочная таблица
10. Апельсинки → backlog (транзакционная таблица баллов)
11. Аватар + районный рейтинг → backlog

## Артефакты сессии
- Схема таблиц: `schema.md` (готово для SQL / Mermaid)
- Беклог: `BACKLOG.md`

Full session: brainstorm-database-schema-mvp-review-20260903-1334.md
