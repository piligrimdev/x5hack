# Brainstorm: nginx-reverse-proxy-vs-fastapi-single-instance
Date: 2026-09-05 16:58
Technique(s) used: TBD

## [MAIN] nginx-reverse-proxy-vs-fastapi-single-instance


## Контекст (реализация)
- **Web**: FastAPI + uvicorn (single process, без `--workers`)
- **docker-compose**: web, worker (celery ×4), beat, db (postgres), redis
- **Порт**: 8000 пробрасывается напрямую на хост — нет SSL-терминации, нет nginx
- **Dockerfile**: python:3.12-slim, poetry install, entrypoint.sh
- **Нет**: nginx.conf, static-файлов в volumes, rate-limit конфига

## [MAIN] nginx reverse proxy — нужен или нет на single instance?

