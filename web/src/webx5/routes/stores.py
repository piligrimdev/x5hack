from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from webx5.dependencies.auth import TerminalTokenDep
from webx5.dependencies.db import SessionDep
from webx5.schemas.store import StoreCreate, StoreFormatResponse, StoreResponse, StoreUpdate

stores_router = APIRouter(prefix="/stores", tags=["Stores"])


@stores_router.get("", response_model=list[StoreResponse])
def list_stores(session: SessionDep) -> list[StoreResponse]:
    from webx5.crud.store import StoreRepository

    repo = StoreRepository()
    stores = repo.list_all(session)
    return [StoreResponse.from_store(s) for s in stores]


@stores_router.get("/formats", response_model=list[StoreFormatResponse])
def list_formats(session: SessionDep) -> list[StoreFormatResponse]:
    from webx5.crud.store import StoreRepository

    repo = StoreRepository()
    return repo.list_formats(session)


@stores_router.get("/{store_id}", response_model=StoreResponse)
def get_store(store_id: uuid.UUID, session: SessionDep) -> StoreResponse:
    from webx5.crud.store import StoreRepository

    repo = StoreRepository()
    store = repo.get_by_id(session, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return StoreResponse.from_store(store)


@stores_router.post("", response_model=StoreResponse, status_code=201)
def create_store(
    data: StoreCreate,
    session: SessionDep,
    _terminal: TerminalTokenDep,
) -> StoreResponse:
    from webx5.crud.store import StoreRepository

    repo = StoreRepository()
    format_ = repo.get_format_by_id(session, data.format_id)
    if not format_:
        raise HTTPException(status_code=404, detail="Store format not found")
    store = repo.create(session, data.model_dump())
    return StoreResponse.from_store(store)


@stores_router.put("/{store_id}", response_model=StoreResponse)
def update_store(
    store_id: uuid.UUID,
    data: StoreUpdate,
    session: SessionDep,
    _terminal: TerminalTokenDep,
) -> StoreResponse:
    from webx5.crud.store import StoreRepository

    repo = StoreRepository()
    update_data = data.model_dump(exclude_none=True)
    if "format_id" in update_data:
        fmt = repo.get_format_by_id(session, update_data["format_id"])
        if not fmt:
            raise HTTPException(status_code=404, detail="Store format not found")
    store = repo.update(session, store_id, update_data)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return StoreResponse.from_store(store)
