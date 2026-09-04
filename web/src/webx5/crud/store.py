from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from webx5.entities.store import Store, StoreFormat


class StoreRepository:
    def list_all(self, session: Session) -> list[Store]:
        return list(session.scalars(select(Store).order_by(Store.geo_cluster)))

    def get_by_id(self, session: Session, store_id: uuid.UUID) -> Store | None:
        return session.get(Store, store_id)

    def list_formats(self, session: Session) -> list[StoreFormat]:
        return list(session.scalars(select(StoreFormat).order_by(StoreFormat.name)))

    def get_format_by_id(self, session: Session, format_id: uuid.UUID) -> StoreFormat | None:
        return session.get(StoreFormat, format_id)

    def get_format_by_name(self, session: Session, name: str) -> StoreFormat | None:
        return session.scalar(select(StoreFormat).where(StoreFormat.name == name))

    def get_or_create_format(self, session: Session, name: str) -> StoreFormat:
        existing = self.get_format_by_name(session, name)
        if existing:
            return existing
        sf = StoreFormat(id=uuid.uuid4(), name=name)
        session.add(sf)
        session.flush()
        return sf

    def create(self, session: Session, data: dict) -> Store:
        store = Store(
            id=uuid.uuid4(),
            format_id=data["format_id"],
            geo_cluster=data["geo_cluster"],
            address=data.get("address"),
        )
        session.add(store)
        session.commit()
        session.refresh(store)
        return store

    def update(self, session: Session, store_id: uuid.UUID, data: dict) -> Store | None:
        store = session.get(Store, store_id)
        if not store:
            return None
        for field in ("format_id", "geo_cluster", "address"):
            if field in data:
                setattr(store, field, data[field])
        session.commit()
        session.refresh(store)
        return store

    def get_store_for_chain(self, session: Session, chain_name: str) -> Store | None:
        sf = self.get_format_by_name(session, chain_name)
        if not sf:
            return None
        return session.scalar(select(Store).where(Store.format_id == sf.id).limit(1))
