"""Policy-gated contract for the isolated renderer worker.

The API never starts a browser or forwards cookies. A deployment may connect an
isolated renderer only after both the global flag and domain registry are set.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlparse

from app.core.config import get_person_search_settings
from app.services.person_search import BLOCKED_CAPTURE_DOMAINS, _domain_matches


@dataclass(frozen=True)
class FetchTicket:
    token: str
    expires_at: int


def issue_fetch_ticket(url: str, *, job_id: str) -> FetchTicket:
    settings = get_person_search_settings()
    host = (urlparse(url).hostname or "").lower()
    allowlist = {item.strip().lower() for item in os.getenv("PERSON_HEADLESS_ALLOWED_DOMAINS", "").split(",") if item.strip()}
    secret = os.getenv("PERSON_FETCH_TICKET_SIGNING_KEY")
    if not settings.headless_enabled or not secret:
        raise PermissionError("headless_disabled")
    if not host or _domain_matches(host, BLOCKED_CAPTURE_DOMAINS) or not _domain_matches(host, allowlist):
        raise PermissionError("headless_domain_not_allowed")
    expires_at = int(time.time()) + 30
    body = json.dumps({"url": url, "job_id": job_id, "exp": expires_at}, separators=(",", ":"), sort_keys=True)
    signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return FetchTicket(token=f"{body}.{signature}", expires_at=expires_at)


def verify_fetch_ticket(token: str) -> dict[str, object]:
    secret = os.getenv("PERSON_FETCH_TICKET_SIGNING_KEY")
    body, separator, signature = token.rpartition(".")
    if not separator or not secret:
        raise PermissionError("invalid_ticket")
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise PermissionError("invalid_ticket")
    payload = json.loads(body)
    if int(payload.get("exp", 0)) <= int(time.time()):
        raise PermissionError("expired_ticket")
    return payload
