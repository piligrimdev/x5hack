from __future__ import annotations

import uuid

from pydantic import BaseModel


class VibeIn(BaseModel):
    name: str
    description: str
    llm_context: str


class VibeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    llm_context: str | None = None


class VibeOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str

    model_config = {"from_attributes": True}
