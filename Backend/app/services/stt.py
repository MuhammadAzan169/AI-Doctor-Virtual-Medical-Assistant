"""Speech-to-text using Whisper. Gated by ENABLE_VOICE; model loads lazily."""

import importlib.util
import os
import tempfile

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("AIDoctor.STT")

_whisper_model = None


def is_available() -> bool:
    """True only when the feature is enabled *and* Whisper is installed."""
    if not settings.ENABLE_VOICE:
        return False
    if importlib.util.find_spec("whisper") is None:
        logger.warning("ENABLE_VOICE=true but openai-whisper is not installed — feature disabled.")
        return False
    return True


def _get_model():
    """Lazily load the Whisper model on first use."""
    global _whisper_model
    if _whisper_model is None:
        import whisper

        logger.info("Loading Whisper model (%s)...", settings.WHISPER_MODEL_SIZE)
        _whisper_model = whisper.load_model(settings.WHISPER_MODEL_SIZE)
        logger.info("Whisper model loaded.")
    return _whisper_model


def transcribe(audio_bytes: bytes, language: str = "en") -> str:
    """Transcribe raw audio bytes to text."""
    if not is_available():
        raise RuntimeError("Voice transcription is not enabled on this server.")

    import torch

    use_fp16 = torch.cuda.is_available()
    model = _get_model()
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        result = model.transcribe(tmp_path, language=language, fp16=use_fp16)
        return result.get("text", "").strip()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
