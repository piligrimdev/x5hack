import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from webx5.dependencies.auth import CurrentUserUUID, TerminalTokenDep
from webx5.dependencies.db import SessionDep
from webx5.schemas.auth import PhoneRequest, RefreshRequest, TokenPairResponse

auth_router = APIRouter(tags=["Auth"])


class VibeSelectRequest(BaseModel):
    vibe_id: uuid.UUID | None


@auth_router.post("/register", response_model=TokenPairResponse)
def register(form: PhoneRequest, session: SessionDep) -> TokenPairResponse:
    from webx5.core.auth import auth_service

    return auth_service.register(form, session)


@auth_router.post("/login", response_model=TokenPairResponse)
def login(form: PhoneRequest, session: SessionDep) -> TokenPairResponse:
    from webx5.core.auth import auth_service

    return auth_service.login(form, session)


@auth_router.post("/refresh", response_model=TokenPairResponse)
def refresh(req: RefreshRequest, session: SessionDep) -> TokenPairResponse:
    from webx5.core.auth import auth_service

    return auth_service.refresh(req, session)


@auth_router.get("/me")
def me(user_id: CurrentUserUUID) -> dict:
    return {"user_id": str(user_id)}


@auth_router.get("/terminal/ping")
def terminal_ping(_: TerminalTokenDep) -> dict:
    return {"status": "ok"}


@auth_router.put("/users/me/vibe")
def set_vibe(
    body: VibeSelectRequest, user_id: CurrentUserUUID, session: SessionDep
) -> dict:
    from webx5.entities.user import User
    from webx5.entities.vibe import VibeType

    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if body.vibe_id is not None:
        vibe = session.get(VibeType, body.vibe_id)
        if vibe is None:
            raise HTTPException(status_code=404, detail="Vibe not found")

    user.vibe_type_id = body.vibe_id
    session.commit()
    return {"vibe_id": str(body.vibe_id) if body.vibe_id else None}
