import os
import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from webx5.utils.auth import decode_access_jwt

_bearer = HTTPBearer(auto_error=False)


def _get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> uuid.UUID:
    if not credentials:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return decode_access_jwt(credentials.credentials)


CurrentUserUUID = Annotated[uuid.UUID, Depends(_get_current_user_id)]


def verify_terminal_token(x_terminal_token: Annotated[str | None, Header()] = None) -> None:
    expected = os.environ.get("TERMINAL_TOKEN", "")
    if not x_terminal_token or x_terminal_token != expected:
        raise HTTPException(status_code=401, detail="Invalid terminal token")


TerminalTokenDep = Annotated[None, Depends(verify_terminal_token)]
