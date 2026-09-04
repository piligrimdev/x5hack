from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webx5.entities.base import Base


class StoreFormat(Base):
    __tablename__ = "store_formats"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    stores: Mapped[list[Store]] = relationship(back_populates="format", lazy="select")


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    format_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("store_formats.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    geo_cluster: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    format: Mapped[StoreFormat] = relationship(back_populates="stores", lazy="joined")
