# Скрипты и сервисы

**Когда применять:** написание или ревью Python-кода в `src/data/scripts/`, `src/rag/`,
`src/**/services/`, `src/**/routes/`, `src/**/crud/`, `src/**/schemas/`, `src/**/entities/`,
`src/**/dependencies/`, `src/**/database/`, `src/**/core/`, `src/**/utils/`, `src/**/main.py`,
а также `tests/`, `Dockerfile`, `docker/**`, `pyproject.toml`, `poetry.lock`.

Перед реализацией читай [fastapi-rest-api.md](fastapi-rest-api.md) для FastAPI-специфики.

## Принципы

Код — SOLID и KISS. DRY — уместно: если задача или техдолг не подразумевают переиспользования,
DRY можно пренебречь.

Комментариями, методами со сложной цепочкой вызовов и абстракциями данных в отдельные классы
можно пренебречь, если:

1. Есть готовая реализация через методы библиотек
2. В задаче указано, что требуется простая, быстрая реализация

## Скрипты

Скрипты — для тестирования функционала и экспериментов (вручную или через агента).

- Без CLI-аргументов; конфиг — envars или `.json`
- Логика в переиспользуемых функциях: интеграция в сервис или Airflow DAG — с минимальными изменениями
- Логирование: `print`

## Сервисы

Слои Repository–Service–Interface, чтобы покрывать unit-тестами.

| Слой | Ответственность |
|---|---|
| Repository | Доступ к данным (SQLAlchemy/DB или `.json`). В FastAPI-пакете — `crud/` |
| Service | Бизнес-логика: валидация, обработка, запуск job-ов. Repository — через DI. В FastAPI-пакете — `services/` |
| Interface | Точка входа: FastAPI `routes/`, `main()` скрипта или callable Airflow task. Принимает данные запроса, отдаёт результат, запускает сервисы |

Важнейший принцип — Dependency Injection: сервис получает репозиторий снаружи, не создаёт его сам.

Инициализация сервисов, подключений к БД, логирования и wiring — контролируемая: импорт конкретного
сервиса для unit-теста не должен запускать остальной код. Сборка — в `if __name__ == "__main__"`,
`core/` + `main.py` FastAPI-пакета, `lifespan` или фабрике, не на уровне модулей
`crud`/`services`/`routes`.

Логирование сервисов и кода, который пойдёт в DAG/API: `structlog`.

Unit-тесты: `tests/` зеркалирует `src/` (`tests/rag/...`, `tests/data/scripts/...`).

## Зависимости

Контейнеризируемые модули (API, DAG runtime, любые образы с Python-кодом) — зависимости только
через Poetry: `pyproject.toml` + `poetry.lock`. В Dockerfile: `poetry install`, не
`pip install -r requirements*.txt` и не ad-hoc `pip install пакет`.

Исключение: Jupyter-ноутбуки (`.ipynb`) — Poetry не обязателен.

```dockerfile
# ❌ BAD
COPY requirements-api.txt .
RUN pip install -r requirements-api.txt

# ✅ GOOD
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main
```

## Проверки после кода

Форматирование, линт и тесты запускай через subagent `lint-format`. Сам команды не выполняй.

Команды (cwd — корень репозитория; `{service_name}` — каталог под `src/`, например `rag` или
`data/scripts`):

- format: `poetry -C src/tooling run ruff format ../{service_name}`
- lint: `poetry -C src/tooling run ruff check ../{service_name} --fix`
