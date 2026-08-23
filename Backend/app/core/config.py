"""Application configuration — single source of truth, loaded from the environment.

Filesystem paths resolve relative to the backend root so the service behaves
identically regardless of the current working directory. Heavy ML features
(fracture detection, OCR, voice) are opt-in via flags so the core LLM
consultation can run on a modest instance.
"""

from __future__ import annotations

import os as _os
import re as _re
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> parents[2] == backend/
BASE_DIR: Path = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────────────────────
    APP_NAME: str = "AI Doctor — Virtual Medical Assistant"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # ── CORS ───────────────────────────────────────────────────────────────
    # Defaults to "*" (all origins) — public API, no credentials. Set to a
    # specific Vercel URL via the ALLOWED_ORIGINS env var to restrict in prod.
    ALLOWED_ORIGINS: str = "*"

    # ── LLM (OpenAI-compatible, e.g. OpenRouter) ──────────────────────────--
    LLM_PROVIDER: str = "openrouter"
    LLM_MODEL: str = "openai/gpt-oss-20b:free"
    LLM_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_MAX_TOKENS: int = 3000
    LLM_TEMPERATURE: float = 0.3
    LLM_API_KEY: str = ""

    # Model chain — tried in order when a model fails across all keys
    OPENROUTER_MODEL_1: str = ""
    OPENROUTER_MODEL_2: str = ""
    OPENROUTER_MODEL_3: str = ""
    OPENROUTER_MODEL_4: str = ""
    OPENROUTER_MODEL_5: str = ""

    OPENROUTER_BASE_URL: str = ""

    # ── Consultation ───────────────────────────────────────────────────────
    MAX_QUESTIONS: int = 8
    MAX_MESSAGE_LENGTH: int = 5000
    MAX_UPLOAD_SIZE_MB: int = 10
    SESSION_TTL_SECONDS: int = 3600

    # ── Optional ML features (heavy — opt-in) ──────────────────────────────
    ENABLE_FRACTURE: bool = False   # TensorFlow ResNet50 X-ray models (~376 MB)
    ENABLE_OCR: bool = False        # PaddleOCR lab-report reading
    ENABLE_VOICE: bool = False      # Whisper speech-to-text (~1.5 GB)
    WHISPER_MODEL_SIZE: str = "medium"
    MODELS_DIR: str = ""            # defaults to backend/fracture_models

    # ── Runtime (writable) directory ───────────────────────────────────────
    RUNTIME_DIR: str = ""           # defaults to backend/var

    # ── Derived values ─────────────────────────────────────────────────────
    @property
    def cors_origins(self) -> List[str]:
        v = self.ALLOWED_ORIGINS.strip()
        if v in ("", "*"):
            return ["*"]
        return [o.strip() for o in v.split(",") if o.strip()]

    @property
    def api_keys(self) -> List[str]:
        """All unique LLM API keys, primary first, then OPENROUTER_API_KEY1..N.

        Numbered keys are collected from the process environment (how Render and
        other hosts supply them) *and* from the local .env file, so the same code
        path works locally and in production.
        """
        candidates: list[str] = [self.LLM_API_KEY]
        pat = _re.compile(r"^OPENROUTER_API_KEY(\d+)$")
        numbered: dict[int, str] = {}

        # 1) Process environment (production: Render dashboard / platform env vars)
        for name, val in _os.environ.items():
            m = pat.match(name.strip())
            if m and val and val.strip():
                numbered[int(m.group(1))] = val.strip().strip("'\"")

        # 2) Local .env file (development convenience; does not override the env)
        env_file = BASE_DIR / ".env"
        if env_file.exists():
            line_pat = _re.compile(r"^OPENROUTER_API_KEY(\d+)\s*=\s*(.+)")
            try:
                lines = env_file.read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
            for raw in lines:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                m = line_pat.match(line)
                if m:
                    val = m.group(2).strip().strip("'\"")
                    idx = int(m.group(1))
                    if val and idx not in numbered:
                        numbered[idx] = val

        candidates.extend(numbered[k] for k in sorted(numbered))
        seen: list[str] = []
        for k in candidates:
            k = k.strip()
            if k and k not in seen:
                seen.append(k)
        return seen

    @property
    def model_chain(self) -> List[str]:
        """Return the ordered model fallback chain from OPENROUTER_MODEL_1..5, else LLM_MODEL."""
        models: list[str] = []
        for m in [
            self.OPENROUTER_MODEL_1, self.OPENROUTER_MODEL_2, self.OPENROUTER_MODEL_3,
            self.OPENROUTER_MODEL_4, self.OPENROUTER_MODEL_5,
        ]:
            if m and m not in models:
                models.append(m)
        # LLM_MODEL is always kept as the last resort, so a mistyped entry in the
        # OPENROUTER_MODEL_* chain cannot take the whole service down.
        if self.LLM_MODEL and self.LLM_MODEL not in models:
            models.append(self.LLM_MODEL)
        return models

    @property
    def llm_base_url(self) -> str:
        """Effective LLM endpoint. OPENROUTER_BASE_URL is accepted as an alias."""
        return (self.LLM_BASE_URL or self.OPENROUTER_BASE_URL or "").strip()

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def models_dir(self) -> Path:
        if self.MODELS_DIR:
            p = Path(self.MODELS_DIR)
            return p if p.is_absolute() else BASE_DIR / p
        return BASE_DIR / "fracture_models"

    @property
    def assets_dir(self) -> Path:
        return BASE_DIR / "app" / "assets"

    @property
    def runtime_dir(self) -> Path:
        if self.RUNTIME_DIR:
            p = Path(self.RUNTIME_DIR)
            return p if p.is_absolute() else BASE_DIR / p
        return BASE_DIR / "var"

    @property
    def upload_dir(self) -> Path:
        return self.runtime_dir / "uploads"

    @property
    def output_dir(self) -> Path:
        return self.runtime_dir / "output"

    @property
    def pdf_dir(self) -> Path:
        return self.runtime_dir / "pdfs"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"


# Heavy local models that cannot run on a small production instance. Hosted
# free tiers give ~512 MB RAM, while TensorFlow, PaddleOCR and Whisper each
# need far more than that before their weights are even loaded.
_PRODUCTION_DISABLED_FEATURES = ("ENABLE_FRACTURE", "ENABLE_OCR", "ENABLE_VOICE")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production:
        # Forced off rather than merely defaulted off: these would otherwise be
        # switched on by a stray dashboard variable and fail on every request,
        # having already spent seconds attempting the import. Local runs are
        # untouched, so `python app.py` keeps the full stack.
        forced = [f for f in _PRODUCTION_DISABLED_FEATURES if getattr(s, f)]
        for flag in forced:
            object.__setattr__(s, flag, False)
        if forced:
            import logging
            logging.getLogger("AIDoctor.Config").warning(
                "Ignoring %s in production — these models need more memory than a "
                "hosted small instance provides. PDF and DOCX reports still work.",
                ", ".join(forced),
            )
    return s


settings = get_settings()
