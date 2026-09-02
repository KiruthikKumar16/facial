"""Configuration for FastAPI backend."""
from __future__ import annotations

import json
import os
from pathlib import Path
from dotenv import load_dotenv


def _find_root_env() -> Path | None:
    """Walk UP from this file's directory to find the PROJECT-ROOT .env file.

    The project layout is:
        repo/
          .env            <-- we ALWAYS prefer this (single-source-of-truth design)
          backend/
            config.py     <-- __file__ is here
            .env          <-- LEGACY only; ignored if repo-root .env exists

    Priority:
    1. repo/.env (two parents up from backend/config.py)
    2. Any .env found while walking further up (e.g. monorepo scenarios)
    3. backend/.env (legacy fallback; only for setups that haven't migrated yet)
    4. cwd/.env — fallback for Render/Vercel platform-injected envs (no file at all)

    On Render (production), there is usually no .env file (env vars are injected
    by the platform), so this safely returns None -> load_dotenv no-op.
    """
    here = Path(__file__).resolve().parent
    repo_root = here.parent  # facial/  (two levels: facial/backend/config.py -> facial/)

    # 1) Explicit project-root .env first (our single-source-of-truth design)
    candidate = repo_root / ".env"
    if candidate.is_file():
        return candidate

    # 2) Walk further up (monorepo / other nesting scenarios)
    for parent in here.parents:
        if parent == repo_root:
            continue  # already checked above
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate

    # 3) Legacy backend/.env fallback
    legacy = here / ".env"
    if legacy.is_file():
        import warnings
        warnings.warn(
            "Found backend/.env — please migrate its contents to the single SIBLING "
            f"file at {repo_root / '.env'} (see .env.example there). "
            "backend/.env will be ignored in future versions.",
            stacklevel=2,
        )
        return legacy

    return None


_env_path = _find_root_env()
if _env_path is not None:
    load_dotenv(_env_path, override=False)
else:
    load_dotenv()  # fallback: check cwd (Render behaviour)


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


def _parse_float(v: str, default: float) -> float:
    if not v:
        return default
    try:
        return float(v)
    except Exception:
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
        return _parse_int(_get("PORT", "1223"), 1223)

    @property
    def debug(self) -> bool:
        return _parse_bool(_get("DEBUG", "False"), False)

    @property
    def enable_forensic_search(self) -> bool:
        return _parse_bool(_get("ENABLE_FORENSIC_SEARCH", "False"), False)

    @property
    def enable_edge_pipelines(self) -> bool:
        return _parse_bool(_get("ENABLE_EDGE_PIPELINES", "False"), False)

    @property
    def unregistered_similarity_threshold(self) -> float:
        return min(0.99, max(0.50, _parse_float(_get("UNREGISTERED_SIMILARITY_THRESHOLD", "0.75"), 0.75)))


settings = _Settings()
