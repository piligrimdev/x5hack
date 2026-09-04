# Quickstart Validation Guide: Product Catalog

**Branch**: `004-product-catalog-seed` | **Date**: 2026-09-04

Это руководство для сквозной проверки фичи после реализации. Не содержит реализацию — только сценарии валидации.

---

## Prerequisites

1. Docker Desktop запущен
2. `.env` настроен (скопирован из `.env.example`, добавлены):
   - `TERMINAL_TOKEN=test-terminal-secret`
   - `SEED_FILE_PATH=./dataset/products.jsonl` (или путь к тестовому файлу)
3. Стек запущен: `docker compose up --build`
4. Миграции применены автоматически при старте контейнера
5. Доступно: `http://localhost:8000` (или `/docs` для Scalar UI)

---

## Сценарий 1: Seed script — первый запуск

**Цель**: убедиться, что скрипт заполняет БД из JSONL.

```bash
# Создать тестовый JSONL (5 строк, 2 категории)
cat > /tmp/test_products.jsonl << 'EOF'
{"sku_id": "sku_0001", "category": "молочные продукты и яйца", "item": "молоко 2,5%", "regular_unit_price_rub": 135.79, "unit_cost_rub": 63.3, "gross_margin_rub": 72.49}
{"sku_id": "sku_0002", "category": "молочные продукты и яйца", "item": "кефир 1%", "regular_unit_price_rub": 89.90, "unit_cost_rub": 40.0, "gross_margin_rub": 49.9}
{"sku_id": "sku_0003", "category": "хлебобулочные изделия", "item": "батон нарезной", "regular_unit_price_rub": 45.00, "unit_cost_rub": 20.0, "gross_margin_rub": 25.0}
{"sku_id": "sku_0004", "category": "хлебобулочные изделия", "item": "багет французский", "regular_unit_price_rub": 79.00, "unit_cost_rub": 35.0, "gross_margin_rub": 44.0}
{"sku_id": "sku_0005", "category": "молочные продукты и яйца", "item": "йогурт греческий", "regular_unit_price_rub": 95.50, "unit_cost_rub": 45.0, "gross_margin_rub": 50.5}
EOF

SEED_FILE_PATH=/tmp/test_products.jsonl docker compose exec web poetry run python scripts/seed_products.py
```

**Ожидаемый вывод**:
```
Loaded 5 lines from /tmp/test_products.jsonl
Done. Imported: 5, Updated: 0, Skipped: 0
```

---

## Сценарий 2: Seed script — идемпотентность

**Цель**: повторный запуск не создаёт дубликатов.

```bash
# Запустить ещё раз
SEED_FILE_PATH=/tmp/test_products.jsonl docker compose exec web poetry run python scripts/seed_products.py
```

**Ожидаемый вывод**:
```
Done. Imported: 0, Updated: 5, Skipped: 0
```

Количество строк в таблицах не изменилось.

---

## Сценарий 3: Seed script — невалидные строки

```bash
cat > /tmp/bad_products.jsonl << 'EOF'
{"sku_id": "sku_0006", "category": "напитки", "item": "вода", "regular_unit_price_rub": 25.00}
{"category": "напитки", "item": "сок", "regular_unit_price_rub": 60.00}
{"sku_id": "sku_0008", "category": "напитки", "item": "лимонад", "regular_unit_price_rub": 0}
EOF

SEED_FILE_PATH=/tmp/bad_products.jsonl docker compose exec web poetry run python scripts/seed_products.py
```

**Ожидаемый вывод**:
```
WARNING: line 2 missing field 'sku_id', skipping
WARNING: line 3 invalid price 0, skipping
Done. Imported: 1, Updated: 0, Skipped: 2
```

---

## Сценарий 4: GET /catalog/categories (мобильный клиент)

**Цель**: список категорий возвращается авторизованному пользователю.

```bash
# 1. Получить JWT
TOKEN=$(curl -s -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"phone": "+79001234567"}' | jq -r '.access_token')

# 2. Запрос категорий
curl -s http://localhost:8000/catalog/categories \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Ожидаемый ответ**:
```json
[
  { "id": "...", "name": "молочные продукты и яйца" },
  { "id": "...", "name": "хлебобулочные изделия" }
]
```

**Проверить**: запрос без токена возвращает `401`.

---

## Сценарий 5: GET /catalog/products (с фильтром и пагинацией)

```bash
# Получить category_id
CAT_ID=$(curl -s http://localhost:8000/catalog/categories \
  -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id')

# Список товаров категории, страница 1, размер 2
curl -s "http://localhost:8000/catalog/products?category_id=$CAT_ID&page=1&size=2" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Ожидаемый ответ**:
```json
{
  "items": [
    {
      "id": "...",
      "sku_id": "sku_0001",
      "name": "молоко 2,5%",
      "current_price": "135.79",
      "category": { "id": "...", "name": "молочные продукты и яйца" }
    },
    { "..." }
  ],
  "total": 3,
  "page": 1,
  "size": 2,
  "pages": 2
}
```

---

## Сценарий 6: GET /catalog/products/{sku_id} (кассовый аппарат)

```bash
# Успешный lookup
curl -s http://localhost:8000/catalog/products/sku_0001 \
  -H "Authorization: Bearer $TOKEN" | jq .

# Несуществующий SKU → 404
curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:8000/catalog/products/sku_9999 \
  -H "Authorization: Bearer $TOKEN"
```

**Ожидаемый ответ (lookup)**:
```json
{
  "id": "...",
  "sku_id": "sku_0001",
  "name": "молоко 2,5%",
  "current_price": "135.79",
  "category": { "id": "...", "name": "молочные продукты и яйца" }
}
```

---

## Сценарий 7: Write endpoints (кассовый аппарат)

```bash
TERMINAL_TOKEN=test-terminal-secret

# Создать категорию
curl -s -X POST http://localhost:8000/catalog/categories \
  -H "X-Terminal-Token: $TERMINAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "замороженные продукты"}' | jq .

# Создать товар
curl -s -X POST http://localhost:8000/catalog/products \
  -H "X-Terminal-Token: $TERMINAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sku_id": "sku_9001", "name": "пицца замороженная", "current_price": 249.90, "category_id": "..."}' | jq .

# Обновить цену
curl -s -X PUT http://localhost:8000/catalog/products/sku_9001 \
  -H "X-Terminal-Token: $TERMINAL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"current_price": 199.90}' | jq .

# Удалить
curl -s -X DELETE http://localhost:8000/catalog/products/sku_9001 \
  -H "X-Terminal-Token: $TERMINAL_TOKEN" -w "%{http_code}"
# Ожидаемо: 204
```

---

## Сценарий 8: Unit tests

```bash
cd web
poetry run pytest tests/webx5/services/test_catalog.py -v
```

Тесты покрывают `CatalogService`:
- `test_get_or_create_category_existing`
- `test_get_or_create_category_new`
- `test_create_product`
- `test_upsert_product_updates_price`
- `test_get_product_by_sku_not_found`

---

## Чеклист итоговой валидации

- [ ] seed script загружает 5 тестовых строк без ошибок
- [ ] повторный запуск seed: 0 новых строк
- [ ] невалидные строки пропускаются, остальные импортируются
- [ ] GET /catalog/categories возвращает список категорий
- [ ] GET /catalog/products с фильтром по category_id возвращает только нужные товары
- [ ] GET /catalog/products возвращает `pages`, `total` в ответе
- [ ] GET /catalog/products/{sku_id} возвращает карточку товара
- [ ] GET /catalog/products/unknown-sku → 404
- [ ] любой GET без JWT → 401
- [ ] POST /catalog/products с TerminalToken создаёт товар
- [ ] POST /catalog/products без TerminalToken → 401
- [ ] PUT обновляет поля товара
- [ ] DELETE удаляет товар (последующий GET → 404)
- [ ] unit tests проходят
