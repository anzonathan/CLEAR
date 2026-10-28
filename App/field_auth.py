"""Optional shared-password protection for the field console.

Set ``CLEAR_FIELD_PASSWORD`` in Coolify. When unset the app stays open, which is
only acceptable behind a private tunnel or VPN.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Optional

from fastapi import Request, WebSocket

COOKIE_NAME = "clear_field_auth"
_SALT = "clear-field-v1"


def field_auth_enabled() -> bool:
    return bool(os.getenv("CLEAR_FIELD_PASSWORD", ""))


def auth_digest(password: Optional[str] = None) -> str:
    secret = password if password is not None else os.getenv("CLEAR_FIELD_PASSWORD", "")
    return hashlib.sha256(f"{_SALT}:{secret}".encode("utf-8")).hexdigest()


def request_authenticated(request: Request) -> bool:
    if not field_auth_enabled():
        return True
    return hmac.compare_digest(request.cookies.get(COOKIE_NAME, ""), auth_digest())


def websocket_authenticated(websocket: WebSocket) -> bool:
    if not field_auth_enabled():
        return True
    return hmac.compare_digest(websocket.cookies.get(COOKIE_NAME, ""), auth_digest())


def password_matches(password: str) -> bool:
    expected = os.getenv("CLEAR_FIELD_PASSWORD", "")
    return bool(expected) and hmac.compare_digest(password, expected)


def protected_path(path: str) -> bool:
    return (
        path == "/field"
        or path.startswith("/field/")
        or path == "/camera"
        or path.startswith("/camera/")
        or path.startswith("/api/field/")
        or path.startswith("/ws/field/")
    )
