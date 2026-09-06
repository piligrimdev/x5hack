from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webx5.crud.vibe import VibeRepository
from webx5.entities.vibe import VibeType


class VibeService:
    def __init__(self, repo: VibeRepository) -> None:
        self.repo = repo

    def create(
        self, session: Session, *, name: str, description: str, llm_context: str
    ) -> VibeType:
        try:
            vibe = self.repo.create(
                session, name=name, description=description, llm_context=llm_context
            )
            session.commit()
            return vibe
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                status_code=409, detail=f"Vibe with name '{name}' already exists"
            )

    def get_all(self, session: Session) -> list[VibeType]:
        return self.repo.get_all(session)

    def get_or_404(self, session: Session, vibe_id: uuid.UUID) -> VibeType:
        vibe = self.repo.get_by_id(session, vibe_id)
        if vibe is None:
            raise HTTPException(status_code=404, detail="Vibe not found")
        return vibe

    def update(
        self,
        session: Session,
        vibe_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        llm_context: str | None = None,
    ) -> VibeType:
        vibe = self.get_or_404(session, vibe_id)
        try:
            updated = self.repo.update(
                session,
                vibe,
                name=name,
                description=description,
                llm_context=llm_context,
            )
            session.commit()
            return updated
        except IntegrityError:
            session.rollback()
            raise HTTPException(
                status_code=409, detail=f"Vibe with name '{name}' already exists"
            )

    def delete(self, session: Session, vibe_id: uuid.UUID) -> None:
        vibe = self.get_or_404(session, vibe_id)
        self.repo.delete(session, vibe)
        session.commit()
