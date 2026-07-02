from dataclasses import dataclass
import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


@dataclass(frozen=True)
class OpenApiSettings:
    service_key: str
    service_key_is_encoded: bool


@dataclass(frozen=True)
class CacheSettings:
    valkey_url: str | None
    ttl_seconds: int


def get_open_api_settings() -> OpenApiSettings:
    load_dotenv()

    decoding_key = os.getenv("OPEN_API_DECODING_KEY")
    if decoding_key:
        return OpenApiSettings(
            service_key=decoding_key,
            service_key_is_encoded=False,
        )

    encoding_key = os.getenv("OPEN_API_ENCODING_KEY")
    if encoding_key:
        return OpenApiSettings(
            service_key=encoding_key,
            service_key_is_encoded=True,
        )

    raise RuntimeError(
        "OPEN_API_DECODING_KEY or OPEN_API_ENCODING_KEY must be configured"
    )


def get_searchapi_api_key() -> str:
    load_dotenv()

    api_key = os.getenv("SEARCHAPI_API_KEY")
    if api_key:
        return api_key

    raise RuntimeError("SEARCHAPI_API_KEY must be configured")


def get_cache_settings() -> CacheSettings:
    load_dotenv()

    ttl = os.getenv("CACHE_TTL_SECONDS", "3600")
    return CacheSettings(
        valkey_url=os.getenv("VALKEY_URL"),
        ttl_seconds=int(ttl),
    )
