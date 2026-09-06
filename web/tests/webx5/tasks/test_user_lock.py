from __future__ import annotations

import uuid

from sqlalchemy.dialects import postgresql
from sqlalchemy import select

from webx5.entities.user import User


def test_user_for_update_without_vibe_join():
    """Lock via `User.id` alone, not the full entity.

    An earlier version of this lock used `select(User).options(noload(User.vibe_type))`
    — that also avoided the JOIN (which is why this test originally checked
    for its absence), but loading the full `User` entity with `vibe_type`
    forced to `noload` planted a vibe_type-less `User` in the session's
    identity map: any LATER same-session `session.get(User, id)` (e.g.
    `ChallengeAdapter.build_profile`) returned that SAME cached instance
    instead of issuing a fresh, properly-joined query — silently ignoring
    the user's actually-selected vibe in favor of the hash-rotated fallback
    theme (see `tasks/generation.py`/`tasks/receipt.py`). Selecting only
    `User.id` never populates a `User` ORM instance at all, so it can't
    poison anything.
    """
    stmt = select(User.id).where(User.id == uuid.uuid4()).with_for_update()
    sql = str(stmt.compile(dialect=postgresql.dialect()))

    assert "FOR UPDATE" in sql
    assert "JOIN" not in sql
