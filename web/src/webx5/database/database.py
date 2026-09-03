from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


class Database:
    def __init__(self, db_uri: str) -> None:
        self.engine = create_engine(db_uri, pool_pre_ping=True)
        self.session = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

    def get_db(self) -> Generator[Session, None, None]:
        with self.session() as session:
            yield session

    @contextmanager
    def get_sync_session(self) -> Generator[Session, None, None]:
        session = self.session()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
