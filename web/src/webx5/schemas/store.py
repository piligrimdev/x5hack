from __future__ import annotations

import uuid

from pydantic import BaseModel


class StoreFormatResponse(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class StoreResponse(BaseModel):
    id: uuid.UUID
    format_id: uuid.UUID
    format_name: str
    geo_cluster: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_store(cls, store) -> "StoreResponse":
        return cls(
            id=store.id,
            format_id=store.format_id,
            format_name=store.format.name,
            geo_cluster=store.geo_cluster,
        )


class StoreCreate(BaseModel):
    format_id: uuid.UUID
    geo_cluster: str
    address: str | None = None


class StoreUpdate(BaseModel):
    format_id: uuid.UUID | None = None
    geo_cluster: str | None = None
    address: str | None = None
