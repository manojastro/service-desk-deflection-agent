from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Annotated, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.api.app.config import get_settings
from apps.api.app.db import Database, password_hash
from packages.shared.schemas import Role, UserContext


bearer = HTTPBearer(auto_error=False)


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_token(user_id: str, ttl_seconds: int = 28_800) -> str:
    settings = get_settings()
    payload = _encode(json.dumps({"sub": user_id, "exp": int(time.time()) + ttl_seconds}, separators=(",", ":")).encode())
    signature = _encode(hmac.new(settings.auth_secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def authenticate(db: Database, username: str, password: str) -> dict | None:
    row = db.fetchone("SELECT * FROM users WHERE username=?", (username.strip().lower(),))
    if not row or not hmac.compare_digest(row["password_hash"], password_hash(password)):
        return None
    return row


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> UserContext:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    try:
        payload, signature = credentials.credentials.split(".", 1)
        expected = _encode(hmac.new(get_settings().auth_secret.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        claims = json.loads(_decode(payload))
        if int(claims["exp"]) < int(time.time()):
            raise ValueError("expired")
    except (ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from None
    row = Database().fetchone("SELECT * FROM users WHERE id=?", (claims["sub"],))
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return UserContext(id=row["id"], username=row["username"], display_name=row["display_name"], role=Role(row["role"]), department=row["department"])


CurrentUser = Annotated[UserContext, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable:
    def dependency(user: CurrentUser) -> UserContext:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return dependency

