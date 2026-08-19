"""LLM client — OpenAI-compatible chat with multi-key rotation and multi-model fallback.

Fallback strategy per call:
  1. Try the current key against the current model.
  2. AuthenticationError / RateLimitError / InternalServerError → rotate to next key.
  3. All keys exhausted for this model, OR model not found (404) → shift to next model,
     reset key index to 0, and retry from step 1.
  4. All models exhausted → raise the last error.
"""

import re
import time
from typing import List, Optional

from openai import (
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    OpenAI,
    RateLimitError,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("AIDoctor.LLM")

SYSTEM_PROMPT = """You are a board-certified virtual physician assistant (AI Doctor).
You follow evidence-based clinical guidelines and practice safe, conservative medicine.

Rules:
- Ask clear, targeted follow-up questions to narrow down the diagnosis.
- Never make definitive diagnoses for serious conditions without sufficient information.
- Always recommend in-person follow-up for any concerning symptoms.
- Use generic medication names when possible.
- Consider patient age, gender, and any provided lab/imaging results.
- Be empathetic but professional.
- If you detect potentially dangerous symptoms (chest pain, difficulty breathing, etc.), advise the patient to seek emergency care immediately.
- Do NOT prescribe controlled substances.
"""

# Errors that mean "this key is bad/exhausted — try the next key"
_KEY_ROTATE_ON = (AuthenticationError, RateLimitError, InternalServerError)

# Errors that mean "this MODEL is unusable — no point trying other keys".
# Providers report an unknown/mistyped model id as either 404 or 400.
_MODEL_SHIFT_ON = (NotFoundError, BadRequestError)


class LLMUnavailableError(RuntimeError):
    """Raised when every configured model/key combination has failed."""


_CONTROL_TOKEN_RE = re.compile(r"<\|[^|>]*\|>")
_CHANNEL_PREAMBLE_RE = re.compile(
    r"^\s*(?:assistant|analysis|final|commentary)+\s*", re.IGNORECASE
)


def sanitize_output(content: str) -> str:
    """Strip chat-template control tokens that some models leak into their reply.

    Harmony-style models (e.g. openai/gpt-oss-*) occasionally emit raw scaffolding
    such as `<|end|><|start|>assistant<|channel|>analysis<|message|>real answer`.
    The real reply is whatever follows the LAST `<|message|>` marker; anything
    else is template noise that must never reach the patient.
    """
    if not content or "<|" not in content:
        return content.strip() if content else ""
    if "<|message|>" in content:
        content = content.rsplit("<|message|>", 1)[1]
    content = _CONTROL_TOKEN_RE.sub(" ", content)
    # Only safe once we know this really was template scaffolding, so a normal
    # reply beginning with "Analysis: ..." is never mangled.
    content = _CHANNEL_PREAMBLE_RE.sub("", content)
    return content.strip()


class LLMClient:
    """OpenAI-compatible client with per-key rotation and per-model fallback."""

    def __init__(self) -> None:
        self.api_keys: List[str] = settings.api_keys
        self.model_chain: List[str] = settings.model_chain
        self._key_idx = 0
        self._model_idx = 0
        self._client: Optional[OpenAI] = None
        if not self.api_keys:
            logger.warning("⚠️  No LLM API keys configured — LLM calls will fail")
        else:
            self._rebuild_client()
        logger.info(
            "LLM provider=%s  models=%d %s  keys=%d",
            settings.LLM_PROVIDER,
            len(self.model_chain), self.model_chain,
            len(self.api_keys),
        )

    # ── Internal helpers ───────────────────────────────────────────────────

    def _rebuild_client(self) -> None:
        self._client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=self.api_keys[self._key_idx],
        )

    @property
    def _current_model(self) -> str:
        return self.model_chain[self._model_idx]

    def _rotate_key(self) -> bool:
        """Advance to the next API key. Returns False when all keys are exhausted."""
        if self._key_idx + 1 >= len(self.api_keys):
            logger.error(
                "All %d keys exhausted for model '%s'.",
                len(self.api_keys), self._current_model,
            )
            return False
        self._key_idx += 1
        self._rebuild_client()
        logger.warning(
            "Rotating to key %d/%d  (model=%s).",
            self._key_idx + 1, len(self.api_keys), self._current_model,
        )
        return True

    def _shift_model(self) -> bool:
        """Advance to the next model and reset key index. Returns False when all models exhausted."""
        if self._model_idx + 1 >= len(self.model_chain):
            logger.error(
                "All %d models with all %d keys exhausted — giving up.",
                len(self.model_chain), len(self.api_keys),
            )
            return False
        prev = self._current_model
        self._model_idx += 1
        self._key_idx = 0
        self._rebuild_client()
        logger.warning(
            "Shifting from model '%s' → '%s' (%d/%d).",
            prev, self._current_model, self._model_idx + 1, len(self.model_chain),
        )
        return True

    @staticmethod
    def _normalize_messages(messages: list) -> list:
        """Convert system messages to user/assistant turns for models lacking system-role support."""
        normalized: list = []
        system_parts: list[str] = []
        for msg in messages:
            if msg["role"] == "system":
                system_parts.append(msg["content"])
            else:
                if system_parts:
                    normalized.append({"role": "user", "content": "[Instructions]\n" + "\n\n".join(system_parts)})
                    normalized.append({"role": "assistant", "content": "Understood. I will follow these instructions."})
                    system_parts = []
                normalized.append(msg)
        if system_parts:
            normalized.append({"role": "user", "content": "[Instructions]\n" + "\n\n".join(system_parts)})
            normalized.append({"role": "assistant", "content": "Understood."})
        return normalized

    # ── Core call with key-rotation + model-shift fallback ─────────────────

    def _call(
        self,
        messages: list,
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str:
        if not self.api_keys:
            raise LLMUnavailableError("No LLM API key configured (set LLM_API_KEY)")
        if not self.model_chain:
            raise LLMUnavailableError("No LLM model configured (set LLM_MODEL)")

        # Always start from key 0, model 0 on each new top-level request
        self._key_idx = 0
        self._model_idx = 0
        self._rebuild_client()

        normalized = self._normalize_messages(messages)
        last_err: Exception = RuntimeError("LLM call failed")

        while True:  # model loop — advances on NotFoundError or key exhaustion
            while True:  # key loop — advances on key-level errors
                try:
                    kwargs: dict = dict(
                        model=self._current_model,
                        messages=normalized,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    if json_mode:
                        kwargs["response_format"] = {"type": "json_object"}

                    start = time.perf_counter()
                    resp = self._client.chat.completions.create(**kwargs)
                    elapsed = (time.perf_counter() - start) * 1000
                    content = sanitize_output(resp.choices[0].message.content or "")
                    logger.info(
                        "LLM OK (%.0fms) chars=%d  key=%d/%d  model=%s",
                        elapsed, len(content),
                        self._key_idx + 1, len(self.api_keys),
                        self._current_model,
                    )
                    return content

                except _MODEL_SHIFT_ON as e:
                    # Model unknown/rejected by the provider — other keys won't help
                    last_err = e
                    logger.warning(
                        "Model '%s' rejected (%s) — skipping to next model.",
                        self._current_model, type(e).__name__,
                    )
                    break  # exit key loop → shift model

                except _KEY_ROTATE_ON as e:
                    last_err = e
                    logger.warning(
                        "Key error on key %d/%d (model=%s): %s",
                        self._key_idx + 1, len(self.api_keys), self._current_model, e,
                    )
                    if not self._rotate_key():
                        break  # all keys exhausted for this model → shift model

            # Key loop exited without a successful response → try next model
            if not self._shift_model():
                raise LLMUnavailableError(
                    "All configured LLM models/keys failed. Last error: %s: %s"
                    % (type(last_err).__name__, last_err)
                ) from last_err

    # ── Public API ─────────────────────────────────────────────────────────

    def ask(
        self,
        messages: list,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        temperature = settings.LLM_TEMPERATURE if temperature is None else temperature
        max_tokens = settings.LLM_MAX_TOKENS if max_tokens is None else max_tokens
        return self._call(messages, temperature, max_tokens, json_mode=False)

    def ask_json(
        self,
        messages: list,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> str:
        max_tokens = settings.LLM_MAX_TOKENS if max_tokens is None else max_tokens
        try:
            return self._call(messages, temperature, max_tokens, json_mode=True)
        except Exception as e:
            # json_object format not supported by any model in the chain → plain text
            logger.warning(
                "JSON mode failed across all models/keys (%s) — retrying as plain text.",
                type(e).__name__,
            )
            return self._call(messages, temperature, max_tokens, json_mode=False)
