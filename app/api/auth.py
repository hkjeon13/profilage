import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException

from app.core.config import get_jwt_settings


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _decode_json_part(value: str) -> dict[str, Any]:
    try:
        decoded = json.loads(_decode_base64url(value))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization token",
        )
    return decoded if isinstance(decoded, dict) else {}


def has_valid_full_response_jwt(authorization: str | None) -> bool:
    if not authorization:
        return False
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    secret = get_jwt_settings().secret
    if not secret:
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    header = _decode_json_part(parts[0])
    payload = _decode_json_part(parts[1])
    if header.get("alg") != "HS256":
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    signing_input = f"{parts[0]}.{parts[1]}".encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    try:
        signature = _decode_base64url(parts[2])
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid authorization token")
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid authorization token")

    exp = payload.get("exp")
    if exp is not None:
        try:
            if float(exp) <= time.time():
                raise HTTPException(
                    status_code=401,
                    detail="Invalid authorization token",
                )
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=401,
                detail="Invalid authorization token",
            )

    return True


def require_admin_jwt(authorization: str | None) -> None:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization is required")
    if not has_valid_full_response_jwt(authorization):
        raise HTTPException(status_code=403, detail="Admin authorization is required")
