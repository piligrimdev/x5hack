from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from webx5.entities.vibe import VibeType


class VibeRepository:
    def create(
        self,
        session: Session,
        *,
        name: str,
        description: str,
        llm_context: str,
    ) -> VibeType:
        vibe = VibeType(
            id=uuid.uuid4(), name=name, description=description, llm_context=llm_context
        )
        session.add(vibe)
        session.flush()
        return vibe

    def get_all(self, session: Session) -> list[VibeType]:
        return list(session.scalars(select(VibeType).order_by(VibeType.name)).all())

    def get_by_id(self, session: Session, vibe_id: uuid.UUID) -> VibeType | None:
        return session.get(VibeType, vibe_id)

    def update(
        self,
        session: Session,
        vibe: VibeType,
        *,
        name: str | None = None,
        description: str | None = None,
        llm_context: str | None = None,
    ) -> VibeType:
        if name is not None:
            vibe.name = name
        if description is not None:
            vibe.description = description
        if llm_context is not None:
            vibe.llm_context = llm_context
        session.flush()
        return vibe

    def delete(self, session: Session, vibe: VibeType) -> None:
        session.delete(vibe)
        session.flush()
