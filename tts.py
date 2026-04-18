import os
import tempfile
import logging
from gtts import gTTS

logger = logging.getLogger(__name__)

MAX_TTS_CHARS = 5000


def text_to_speech_file(text: str, lang: str = "en") -> str:
    """
    Convert text to speech using Google TTS and save as a temporary MP3 file.

    Parameters
    ----------
    text : str
        The text to synthesise.  Truncated to ``MAX_TTS_CHARS`` characters.
    lang : str, optional
        BCP-47 language code (default "en").

    Returns
    -------
    str
        Absolute path to the generated MP3 file.  The caller is
        responsible for deleting it after use.

    Raises
    ------
    ValueError
        If *text* is empty.
    RuntimeError
        If gTTS fails (e.g. no internet).
    """
    if not text or not text.strip():
        raise ValueError("Cannot synthesise empty text.")

    if len(text) > MAX_TTS_CHARS:
        logger.warning(
            "TTS text truncated from %d to %d chars", len(text), MAX_TTS_CHARS
        )
        text = text[:MAX_TTS_CHARS]

    try:
        tts = gTTS(text=text, lang=lang, slow=False)
    except Exception as exc:
        raise RuntimeError(f"gTTS initialisation failed: {exc}") from exc

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.close()
    try:
        tts.save(tmp.name)
    except Exception as exc:
        # Clean up partial file on failure
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise RuntimeError(f"gTTS save failed: {exc}") from exc

    return tmp.name
