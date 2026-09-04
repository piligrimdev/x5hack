"""Seed task_status dictionary rows: открыто / выполнено / провалено / истекло.

Idempotent — re-running does not duplicate rows.

Config via env vars (loaded from .env):
  DATABASE_URL     PostgreSQL connection string
"""

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "web" / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / ".env")
load_dotenv()

os.environ.setdefault("DATABASE_URL", os.getenv("DATABASE_URL", ""))

from sqlalchemy import select  # noqa: E402

from webx5.core.db import db  # noqa: E402
from webx5.entities.task import TaskStatus  # noqa: E402

STATUSES = ["открыто", "выполнено", "провалено", "истекло"]


def main() -> None:
    with db.get_sync_session() as session:
        existing = {
            row.name
            for row in session.execute(select(TaskStatus)).scalars().all()
        }
        to_insert = [name for name in STATUSES if name not in existing]
        for name in to_insert:
            session.add(TaskStatus(name=name))
        if to_insert:
            session.commit()
            print(f"Seeded {len(to_insert)} task statuses: {', '.join(to_insert)}")
        else:
            print(f"All {len(STATUSES)} task statuses already present, nothing to do.")


if __name__ == "__main__":
    main()
