Общайся на русском языке.

Read `.specify/memory/constitution.md` first — это источник истины по принципам проекта.

`CONTEXT_PACK.md` - источник контекста проекта, в нем описан кейс, продуктовые требования, гипотезы. Используй его, когда необходимо свериться с направлением.

`README.md` - техническое описание проекта. Структура, архитектура, команды для setup, описание happy-path. Кратко, файл для людей.

`BACKLOG.md` - описание технического долга. В него сгружай то, что касается реализаций, от которых отказались в рамках PoC, MVP для ускорения разработки.

@AGENTS.md

## Правила разработки (читай перед кодом)

При работе с Python-бэкендом (`web/`, `src/**/*.py`, `Dockerfile`, `pyproject.toml`, `poetry.lock`) — читай:

- `.claude/rules/scripts-and-services.md` — SOLID/KISS, RSI, DI, Poetry, structlog, тесты
- `.claude/rules/fastapi-rest-api.md` — структура пакета, session, routes, main.py, авторизация JWT
