import uuid

from sqlalchemy.orm import Session

from webx5.entities.user import User


class UserRepository:
    def get_by_phone(self, session: Session, phone: str) -> User | None:
        return session.query(User).filter(User.phone == phone).first()

    def add(self, session: Session, phone: str) -> User:
        user = User(id=uuid.uuid4(), phone=phone)
        session.add(user)
        session.flush()
        return user

    def create(self, session: Session, phone: str) -> User:
        user = self.add(session, phone)
        session.commit()
        session.refresh(user)
        return user
