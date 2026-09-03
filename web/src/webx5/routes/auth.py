from fastapi import APIRouter

from webx5.dependencies.auth import CurrentUserUUID, TerminalTokenDep
from webx5.dependencies.db import SessionDep
from webx5.schemas.auth import PhoneRequest, RefreshRequest, TokenPairResponse

auth_router = APIRouter(tags=["Auth"])


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
