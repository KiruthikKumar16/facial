"""Configuration for FastAPI backend."""
from __future__ import annotations

import json
import os
from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str = "") -> str:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip()


def _parse_bool(v: str, default: bool = False) -> bool:
    if not v:
        return default
    return v.lower() in ("1", "true", "yes", "on")


def _parse_int(v: str, default: int) -> int:
    if not v:
        return default
    try:
        return int(v)
    except Exception:
        return default


def _split_origins(v: str) -> list[str]:
    if not v:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    if v.startswith("["):
        try:
            parsed = json.loads(v)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except Exception:
            pass
    return [p.strip() for p in v.split(",") if p.strip()]


class _Settings:
    """Application settings read from environment variables."""

    @property
    def database_url(self) -> str:
        return _get(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/facial_recognition",
        )

    @property
    def api_title(self) -> str:
        return _get("API_TITLE", "Facial Recognition API")

    @property
    def api_version(self) -> str:
        return _get("API_VERSION", "1.0.0")

    @property
    def cors_origins(self) -> list[str]:
        return _split_origins(_get("CORS_ORIGINS", ""))

    @property
    def host(self) -> str:
        return _get("HOST", "0.0.0.0")

    @property
    def port(self) -> int:
        return _parse_int(_get("PORT", "8000"), 8000)

    @property
    def debug(self) -> bool:
        return _parse_bool(_get("DEBUG", "False"), False)


settings = _Settings()
