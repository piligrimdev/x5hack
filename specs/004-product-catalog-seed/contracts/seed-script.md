# Contract: Seed Script

**File**: `web/scripts/seed_products.py`

---

## Конфигурация (env vars)

| Variable | Required | Description |
|----------|----------|-------------|
| `SEED_FILE_PATH` | Yes | Абсолютный или относительный путь до JSONL-файла |
| `DATABASE_URL` | Yes | PostgreSQL connection string (уже используется в проекте) |

Переменные читаются из `.env` через `python-dotenv` (тот же паттерн, что у всего проекта).

---

## Входной формат

Файл JSONL: одна JSON-запись на строку, кодировка UTF-8.

**Обязательные поля**:
- `sku_id` (str) — уникальный идентификатор товара
- `item` (str) — название товара
- `category` (str) — название категории
- `regular_unit_price_rub` (float) — цена > 0

**Необязательные поля** (игнорируются, не сохраняются):
- `unit_cost_rub`
- `gross_margin_rub`

**Пример строки**:
```json
{"sku_id": "sku_0000", "category": "молочные продукты и яйца", "item": "молоко", "regular_unit_price_rub": 135.79, "unit_cost_rub": 63.3, "gross_margin_rub": 72.49}
```

---

## Поведение

### Нормальный запуск

1. Читает `SEED_FILE_PATH` из `.env` / переменных окружения
2. Построчно парсит JSONL
3. Для каждой строки:
   a. Проверяет обязательные поля — при отсутствии пропускает с `print(WARNING: ...)`
   b. Проверяет `regular_unit_price_rub > 0` — при нарушении пропускает
   c. Находит или создаёт категорию по имени (INSERT ... ON CONFLICT DO NOTHING)
   d. Делает UPSERT товара по `sku_id` (INSERT ... ON CONFLICT (sku_id) DO UPDATE name, current_price, category_id)
4. Выводит итоговую сводку: `Imported: N, Updated: M, Skipped: K`

### Идемпотентность

Повторный запуск с тем же файлом не увеличивает количество записей. Обновляет `name`, `current_price`, `category_id` существующих товаров.

### Обработка ошибок

| Условие | Поведение |
|---------|-----------|
| `SEED_FILE_PATH` не задан | `sys.exit(1)` с сообщением |
| Файл не найден | `sys.exit(1)` с сообщением |
| Файл пустой | Вывод предупреждения, завершение (0 импортировано) |
| Строка — невалидный JSON | Пропустить строку, `print(WARNING: ...)` |
| Отсутствуют обязательные поля | Пропустить строку, `print(WARNING: ...)` |
| `regular_unit_price_rub <= 0` | Пропустить строку, `print(WARNING: ...)` |
| БД недоступна | Исключение при старте (до обработки строк) |

---

## Запуск

```bash
# из директории web/
SEED_FILE_PATH=../dataset/products.jsonl poetry run python scripts/seed_products.py

# или через .env
echo "SEED_FILE_PATH=../dataset/products.jsonl" >> .env
poetry run python scripts/seed_products.py
```

---

## Ожидаемый stdout

```
Loaded 1000 lines from /path/to/products.jsonl
WARNING: line 42 missing field 'sku_id', skipping
WARNING: line 99 invalid price 0.0, skipping
Done. Imported: 895, Updated: 103, Skipped: 2
```
