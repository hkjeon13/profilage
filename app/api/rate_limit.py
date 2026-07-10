from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException, Request


_summary_windows: dict[str, deque[float]] = defaultdict(deque)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get(
        "x-forwarded-for"
    )
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def enforce_summary_rate_limit(
    request: Request,
    *,
    limit: int,
    window_seconds: int = 60,
) -> None:
    now = monotonic()
    key = _client_key(request)
    window = _summary_windows[key]
    cutoff = now - window_seconds
    while window and window[0] <= cutoff:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Too many summary requests. Please retry later.",
        )
    window.append(now)
