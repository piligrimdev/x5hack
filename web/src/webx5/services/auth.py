from fastapi import HTTPException
from sqlalchemy.orm import Session

from webx5.crud.user import UserRepository
from webx5.schemas.auth import PhoneRequest, RefreshRequest, TokenPairResponse
from webx5.utils.auth import (
    decode_refresh_jwt,
    encode_access_jwt,
    encode_refresh_jwt,
)


class AuthService:
    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    def _issue_pair(self, user_id) -> TokenPairResponse:
        return TokenPairResponse(
            access_token=encode_access_jwt(user_id),
            refresh_token=encode_refresh_jwt(user_id),
        )

    def register(self, form: PhoneRequest, session: Session) -> TokenPairResponse:
        existing = self.user_repo.get_by_phone(session, form.phone)
        if existing:
            raise HTTPException(status_code=409, detail="Phone already registered")
        user = self.user_repo.create(session, form.phone)
        return self._issue_pair(user.id)

    def login(self, form: PhoneRequest, session: Session) -> TokenPairResponse:
        user = self.user_repo.get_by_phone(session, form.phone)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return self._issue_pair(user.id)

    def refresh(self, req: RefreshRequest, session: Session) -> TokenPairResponse:
        from webx5.entities.user import User

        user_id = decode_refresh_jwt(req.refresh_token)
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        return self._issue_pair(user.id)
