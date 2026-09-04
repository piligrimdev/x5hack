FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir poetry \
    && poetry config virtualenvs.create false \
    && poetry config virtualenvs.in-project false

# Build context = repo root. Web-specific files under ./web/, synth under ./synth/, config under ./config/.
COPY web/pyproject.toml web/poetry.lock ./
RUN poetry install --no-root --only main

COPY web/src/ ./src/
COPY web/scripts/ ./scripts/
COPY web/alembic/ ./alembic/
COPY web/alembic.ini ./
COPY web/entrypoint.sh ./
COPY synth/ /app/synth/
COPY config/ /config/
RUN chmod +x entrypoint.sh

# /app/src — webx5 package; /app — allows `import synth`
ENV PYTHONPATH=/app/src:/app

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
