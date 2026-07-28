"""Policy-gated contract for the isolated renderer worker.

The API never starts a browser or forwards cookies. A deployment may connect an
isolated renderer only after both the global flag and domain registry are set.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import json
import os
import time
from urllib.parse import urlparse

from app.core.config import get_person_search_settings
from app.services.person_search import BLOCKED_CAPTURE_DOMAINS, _domain_matches


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class FetchTicket:
    token: str
    expires_at: int


def issue_fetch_ticket(url: str, *, job_id: str) -> FetchTicket:
    settings = get_person_search_settings()
    host = (urlparse(url).hostname or "").lower()
    allowlist = {item.strip().lower() for item in os.getenv("PERSON_HEADLESS_ALLOWED_DOMAINS", "").split(",") if item.strip()}
    signing_key = os.getenv("PERSON_FETCH_TICKET_SIGNING_KEY")
    if not settings.headless_enabled or not signing_key:
        raise PermissionError("headless_disabled")
    if not host or _domain_matches(host, BLOCKED_CAPTURE_DOMAINS) or not _domain_matches(host, allowlist):
        raise PermissionError("headless_domain_not_allowed")
    expires_at = int(time.time()) + 30
    body = json.dumps({"url": url, "job_id": job_id, "exp": expires_at}, separators=(",", ":"), sort_keys=True)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    private_key = Ed25519PrivateKey.from_private_bytes(_b64decode(signing_key))
    body_bytes = body.encode()
    signature = private_key.sign(body_bytes)
    return FetchTicket(token=f"{_b64encode(body_bytes)}.{_b64encode(signature)}", expires_at=expires_at)


def verify_fetch_ticket(token: str) -> dict[str, object]:
    verify_key = os.getenv("PERSON_FETCH_TICKET_VERIFY_KEY")
    encoded_body, separator, encoded_signature = token.partition(".")
    if not separator or not verify_key:
        raise PermissionError("invalid_ticket")
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        body = _b64decode(encoded_body)
        signature = _b64decode(encoded_signature)
        Ed25519PublicKey.from_public_bytes(_b64decode(verify_key)).verify(signature, body)
    except (ValueError, InvalidSignature):
        raise PermissionError("invalid_ticket")
    payload = json.loads(body)
    if int(payload.get("exp", 0)) <= int(time.time()):
        raise PermissionError("expired_ticket")
    return payload
