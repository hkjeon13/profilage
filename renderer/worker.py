from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import socket
import time
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from redis import asyncio as redis

from app.services.headless_fetch import verify_fetch_ticket

VALKEY_URL = os.environ["VALKEY_EPHEMERAL_URL"]
QUEUE_KEY = "person:renderer:queue"
MAX_TEXT_CHARS = min(max(int(os.getenv("PERSON_HEADLESS_MAX_TEXT_CHARS", "25000")), 1000), 50000)
TIMEOUT_MS = min(max(int(float(os.getenv("PERSON_HEADLESS_TIMEOUT_SECONDS", "12")) * 1000), 3000), 20000)
RESULT_TTL = 3600


def _allowed_domains() -> set[str]:
    return {item.strip().lower() for item in os.getenv("PERSON_HEADLESS_ALLOWED_DOMAINS", "").split(",") if item.strip()}


def _host_allowed(host: str) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in _allowed_domains())


async def _assert_public_host(host: str) -> None:
    if not host or not _host_allowed(host):
        raise PermissionError("domain_not_allowed")
    loop = asyncio.get_running_loop()
    records = await loop.run_in_executor(None, lambda: socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
    if not records:
        raise PermissionError("dns_failed")
    for record in records:
        if not ipaddress.ip_address(record[4][0]).is_global:
            raise PermissionError("private_network_blocked")


async def _cancelled(client, job_id: str) -> bool:
    return bool(await client.exists(f"person:cancel:{job_id}"))


async def _store_failed(client, envelope: dict, reason: str) -> None:
    job_id = envelope.get("job_id")
    job = {"job_id": job_id, "intent_id": envelope.get("intent_id"), "session_id": envelope.get("session_id"),
           "status": "failed", "mode": "headless", "reason": reason[:80], "finished_at": int(time.time())}
    await client.set(f"person:job:{job_id}", json.dumps(job, ensure_ascii=False), ex=RESULT_TTL)


async def render_job(client, browser, envelope: dict) -> None:
    job_id = str(envelope.get("job_id") or "")
    if not job_id or int(envelope.get("deadline", 0)) <= int(time.time()) or await _cancelled(client, job_id):
        return
    ticket = verify_fetch_ticket(str(envelope.get("ticket") or ""))
    if ticket.get("job_id") != job_id:
        raise PermissionError("ticket_job_mismatch")
    url = str(ticket.get("url") or "")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise PermissionError("https_required")
    await _assert_public_host((parsed.hostname or "").lower())
    context = await browser.new_context(java_script_enabled=True, accept_downloads=False,
                                        service_workers="block", ignore_https_errors=False)
    page = await context.new_page()

    async def route_request(route):
        request = route.request
        target = urlparse(request.url)
        if target.scheme not in {"https", "data"}:
            await route.abort(); return
        if target.scheme == "https" and not _host_allowed((target.hostname or "").lower()):
            await route.abort(); return
        if request.resource_type in {"image", "media", "font", "websocket", "manifest"}:
            await route.abort(); return
        await route.continue_()

    await page.route("**/*", route_request)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        final_url = page.url
        final_host = (urlparse(final_url).hostname or "").lower()
        await _assert_public_host(final_host)
        if await _cancelled(client, job_id) or int(envelope.get("deadline", 0)) <= int(time.time()):
            return
        title = (await page.title())[:200]
        main = page.locator("main")
        text = await main.inner_text(timeout=2000) if await main.count() == 1 else await page.locator("body").inner_text(timeout=2000)
        text = re.sub(r"\s+", " ", text).strip()[:MAX_TEXT_CHARS]
        if len(text) < 80:
            raise ValueError("insufficient_content")
        if await _cancelled(client, job_id):
            return
        result_id = "par_" + hashlib.sha256(f"{job_id}:{time.time_ns()}".encode()).hexdigest()[:24]
        result = {
            "result_id": result_id, "job_id": job_id, "intent_id": envelope.get("intent_id"),
            "candidate_id": envelope.get("candidate_id"), "page_title": title,
            "domain": final_host, "source_url": final_url,
            "analysis": {"summary": text[:700], "topics": [], "observable_communication_features": [],
                         "limitations": ["JavaScript 렌더링 후 공개 페이지 본문만 추출했으며 자동 해석은 제한했습니다."]},
            "evidence": [{"quote": text[:450], "content_hash": "sha256:" + hashlib.sha256(text.encode()).hexdigest()}],
            "limitations": ["이 결과는 허용된 공개 페이지 한 건의 렌더링 결과만 기반으로 합니다."],
            "expires_in_seconds": int(envelope.get("result_ttl", RESULT_TTL)),
            "subject_identity": envelope.get("subject_identity"), "capture_mode": "headless_public",
        }
        ttl = int(envelope.get("result_ttl", RESULT_TTL))
        await client.set(f"person:result:{result_id}:{envelope['session_id']}", json.dumps(result, ensure_ascii=False), ex=ttl)
        job = {"job_id": job_id, "intent_id": envelope.get("intent_id"), "session_id": envelope.get("session_id"),
               "status": "result_ready", "mode": "headless", "result_id": result_id, "finished_at": int(time.time())}
        await client.set(f"person:job:{job_id}", json.dumps(job, ensure_ascii=False), ex=ttl)
        intent_raw = await client.get(f"person:intent:{envelope.get('intent_id')}")
        if intent_raw:
            intent = json.loads(intent_raw); intent["state"] = "result_ready"
            await client.set(f"person:intent:{envelope.get('intent_id')}", json.dumps(intent, ensure_ascii=False), ex=300)
    finally:
        await context.close()


async def main() -> None:
    client = redis.from_url(VALKEY_URL, decode_responses=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
        try:
            while True:
                await client.set("person:renderer:health", str(int(time.time())), ex=30)
                item = await client.blpop(QUEUE_KEY, timeout=5)
                if not item:
                    continue
                try:
                    envelope = json.loads(item[1])
                    await render_job(client, browser, envelope)
                except Exception as exc:
                    await _store_failed(client, envelope if "envelope" in locals() else {}, type(exc).__name__)
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
