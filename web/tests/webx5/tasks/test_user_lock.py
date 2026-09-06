from __future__ import annotations

import uuid

from sqlalchemy.dialects import postgresql
from sqlalchemy import select
from sqlalchemy.orm import noload

from webx5.entities.user import User


def test_user_for_update_without_vibe_join():
    stmt = (
        select(User)
        .options(noload(User.vibe_type))
        .where(User.id == uuid.uuid4())
        .with_for_update()
    )
    sql = str(stmt.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE" in sql
    assert "JOIN" not in sql
