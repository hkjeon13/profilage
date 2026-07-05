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
    bypass_rate: float


@dataclass(frozen=True)
class DatabaseSettings:
    database_url: str | None


@dataclass(frozen=True)
class OpenAiSettings:
    api_key: str | None
    model: str
    max_chars: int


@dataclass(frozen=True)
class JwtSettings:
    secret: str | None


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


def get_dart_api_key(*, required: bool = True) -> str | None:
    load_dotenv()

    api_key = os.getenv("DART_API_KEY")
    if api_key:
        return api_key
    if not required:
        return None

    raise RuntimeError("DART_API_KEY must be configured")


def get_openai_settings(*, required: bool = True) -> OpenAiSettings:
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if required and not api_key:
        raise RuntimeError("OPENAI_API_KEY must be configured")

    return OpenAiSettings(
        api_key=api_key,
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        max_chars=int(os.getenv("OPENAI_SUMMARY_MAX_CHARS", "18000")),
    )


def get_jwt_settings() -> JwtSettings:
    load_dotenv()

    return JwtSettings(
        secret=os.getenv("PROFILAGE_JWT_SECRET") or os.getenv("JWT_SECRET")
    )


def get_cache_settings() -> CacheSettings:
    load_dotenv()

    ttl = os.getenv("CACHE_TTL_SECONDS", "3600")
    bypass_rate = os.getenv("CACHE_BYPASS_RATE", "0.1")
    return CacheSettings(
        valkey_url=os.getenv("VALKEY_URL"),
        ttl_seconds=int(ttl),
        bypass_rate=min(max(float(bypass_rate), 0.0), 1.0),
    )


def get_database_settings() -> DatabaseSettings:
    load_dotenv()

    return DatabaseSettings(database_url=os.getenv("DATABASE_URL"))
