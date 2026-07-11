import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services.headless_fetch import issue_fetch_ticket, verify_fetch_ticket


def configure_keys(monkeypatch):
    import base64
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                              serialization.NoEncryption())
    public_bytes = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setenv("PERSON_FETCH_TICKET_SIGNING_KEY", base64.urlsafe_b64encode(private_bytes).decode().rstrip("="))
    monkeypatch.setenv("PERSON_FETCH_TICKET_VERIFY_KEY", base64.urlsafe_b64encode(public_bytes).decode().rstrip("="))


def test_fetch_ticket_requires_feature_flag(monkeypatch):
    configure_keys(monkeypatch)
    monkeypatch.setenv("PERSON_HEADLESS_ALLOWED_DOMAINS", "example.com")
    monkeypatch.setenv("PERSON_HEADLESS_ENABLED", "false")
    with pytest.raises(PermissionError, match="headless_disabled"):
        issue_fetch_ticket("https://example.com/profile", job_id="paj_test")


def test_fetch_ticket_is_bound_to_allowlisted_url_and_job(monkeypatch):
    configure_keys(monkeypatch)
    monkeypatch.setenv("PERSON_HEADLESS_ALLOWED_DOMAINS", "example.com")
    monkeypatch.setenv("PERSON_HEADLESS_ENABLED", "true")
    ticket = issue_fetch_ticket("https://www.example.com/profile", job_id="paj_test")
    payload = verify_fetch_ticket(ticket.token)
    assert payload["job_id"] == "paj_test"
    assert payload["url"] == "https://www.example.com/profile"
    assert ticket.expires_at > int(time.time())


def test_fetch_ticket_rejects_social_and_unlisted_domains(monkeypatch):
    configure_keys(monkeypatch)
    monkeypatch.setenv("PERSON_HEADLESS_ALLOWED_DOMAINS", "example.com,linkedin.com")
    monkeypatch.setenv("PERSON_HEADLESS_ENABLED", "true")
    with pytest.raises(PermissionError, match="headless_domain_not_allowed"):
        issue_fetch_ticket("https://linkedin.com/in/person", job_id="paj_test")
    with pytest.raises(PermissionError, match="headless_domain_not_allowed"):
        issue_fetch_ticket("https://not-allowed.test/person", job_id="paj_test")


def test_fetch_ticket_rejects_tampering(monkeypatch):
    configure_keys(monkeypatch)
    monkeypatch.setenv("PERSON_HEADLESS_ALLOWED_DOMAINS", "example.com")
    monkeypatch.setenv("PERSON_HEADLESS_ENABLED", "true")
    ticket = issue_fetch_ticket("https://example.com/profile", job_id="paj_test")
    replacement = "A" if ticket.token[-1] != "A" else "B"
    with pytest.raises(PermissionError, match="invalid_ticket"):
        verify_fetch_ticket(ticket.token[:-1] + replacement)
