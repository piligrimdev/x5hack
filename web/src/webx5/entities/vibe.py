from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Text, UniqueConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from webx5.entities.base import Base


class VibeType(Base):
    __tablename__ = "vibe_type"
    __table_args__ = (
        UniqueConstraint("name", name="uq_vibe_type_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    llm_context: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
