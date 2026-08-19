"""Text-to-speech using Google TTS (gTTS). Lightweight; requires internet."""

import os
import tempfile

from gtts import gTTS

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("AIDoctor.TTS")


def text_to_speech_file(text: str, lang: str = "en") -> str:
    """Synthesize speech to a temporary MP3. Caller is responsible for deletion."""
    if not text or not text.strip():
        raise ValueError("Cannot synthesise empty text.")

    max_chars = settings.MAX_MESSAGE_LENGTH
    if len(text) > max_chars:
        logger.warning("TTS text truncated from %d to %d chars", len(text), max_chars)
        text = text[:max_chars]

    try:
        tts = gTTS(text=text, lang=lang, slow=False)
    except Exception as exc:
        raise RuntimeError(f"gTTS initialisation failed: {exc}") from exc

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.close()
    try:
        tts.save(tmp.name)
    except Exception as exc:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise RuntimeError(f"gTTS save failed: {exc}") from exc
    return tmp.name
