import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from webx5.entities.base import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
