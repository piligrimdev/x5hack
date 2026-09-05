import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from webx5.entities.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    loyalty_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    vibe_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vibe_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
    )
