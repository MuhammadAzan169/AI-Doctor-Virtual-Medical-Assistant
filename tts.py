import os
import tempfile
from gtts import gTTS


def text_to_speech_file(text: str, lang: str = "en") -> str:
    """
    Convert text to speech using Google TTS and save as a temporary MP3 file.

    Parameters
    ----------
    text : str
        The text to synthesise.
    lang : str, optional
        BCP-47 language code (default "en").

    Returns
    -------
    str
        Absolute path to the generated MP3 file.  The caller is
        responsible for deleting it after use.
    """
    tts = gTTS(text=text, lang=lang, slow=False)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.close()
    tts.save(tmp.name)
    return tmp.name
