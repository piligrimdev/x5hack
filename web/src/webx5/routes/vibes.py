from __future__ import annotations

import uuid

from fastapi import APIRouter

from webx5.dependencies.auth import TerminalTokenDep
from webx5.dependencies.db import SessionDep
from webx5.schemas.vibe import VibeIn, VibeOut, VibeUpdate

vibes_router = APIRouter(prefix="/vibes", tags=["Vibes"])


@vibes_router.get("", response_model=list[VibeOut])
def list_vibes(session: SessionDep) -> list[VibeOut]:
    from webx5.core.vibes import vibe_service

    return vibe_service.get_all(session)


@vibes_router.post("", response_model=VibeOut, status_code=201)
def create_vibe(_: TerminalTokenDep, body: VibeIn, session: SessionDep) -> VibeOut:
    from webx5.core.vibes import vibe_service

    return vibe_service.create(
        session,
        name=body.name,
        description=body.description,
        llm_context=body.llm_context,
    )


@vibes_router.put("/{vibe_id}", response_model=VibeOut)
def update_vibe(
    _: TerminalTokenDep, vibe_id: uuid.UUID, body: VibeUpdate, session: SessionDep
) -> VibeOut:
    from webx5.core.vibes import vibe_service

    return vibe_service.update(
        session,
        vibe_id,
        name=body.name,
        description=body.description,
        llm_context=body.llm_context,
    )


@vibes_router.delete("/{vibe_id}", status_code=204)
def delete_vibe(_: TerminalTokenDep, vibe_id: uuid.UUID, session: SessionDep) -> None:
    from webx5.core.vibes import vibe_service

    vibe_service.delete(session, vibe_id)
