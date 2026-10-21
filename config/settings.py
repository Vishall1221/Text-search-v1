"""Single source of runtime configuration for the local application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


CONFIG_DIR = Path(__file__).resolve().parent
load_dotenv(CONFIG_DIR / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql://ai_search@127.0.0.1:5432/ai_search")
    api_host: str = os.getenv("API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("API_PORT", "8000"))
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://127.0.0.1:8081").rstrip("/")
    llm_model: str = os.getenv("LLM_MODEL", "Qwen3-4B-Instruct-2507-Q4_K_M.gguf")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    llm_enabled: bool = os.getenv("LLM_ENABLED", "true").casefold() == "true"
    catalog_cache_seconds: int = int(os.getenv("CATALOG_CACHE_SECONDS", "60"))
    candidate_limit: int = int(os.getenv("CANDIDATE_LIMIT", "250"))
    scenes_per_title: int = int(os.getenv("SCENES_PER_TITLE", "60"))


settings = Settings()
