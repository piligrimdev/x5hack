from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webx5.entities.base import Base

if TYPE_CHECKING:
    from webx5.entities.vibe import VibeType


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    loyalty_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    vibe_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vibe_type.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )

    vibe_type: Mapped["VibeType | None"] = relationship(lazy="joined")
