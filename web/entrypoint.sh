#!/bin/sh
set -e

echo "Running migrations..."
alembic upgrade head || echo "Migration failed, continuing..."

echo "Starting server..."
exec python -m webx5
