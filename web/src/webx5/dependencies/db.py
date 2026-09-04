from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from webx5.core.db import db


def get_db() -> Session:
    yield from db.get_db()


SessionDep = Annotated[Session, Depends(get_db)]
