import os
import tempfile
import torch


def speech_to_text_from_bytes(
    audio_bytes: bytes,
    model,
    language: str = "en",
) -> str:
    """
    Transcribe raw audio bytes using the pre-loaded Whisper model.

    Parameters
    ----------
    audio_bytes : bytes
        Raw audio file content (WAV, MP3, etc.).
    model : whisper.Whisper
        A pre-loaded Whisper model instance.
    language : str
        BCP-47 language code for transcription (default ``"en"``).

    Returns
    -------
    str
        The transcribed text.
    """
    use_fp16 = torch.cuda.is_available()
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


def speech_to_text_from_file(
    file_path: str,
    model,
    language: str = "en",
) -> str:
    """
    Transcribe an audio file on disk using the pre-loaded Whisper model.

    Parameters
    ----------
    file_path : str
        Path to the audio file.
    model : whisper.Whisper
        A pre-loaded Whisper model instance.
    language : str
        BCP-47 language code for transcription (default ``"en"``).

    Returns
    -------
    str
        The transcribed text.
    """
    use_fp16 = torch.cuda.is_available()
    result = model.transcribe(file_path, language=language, fp16=use_fp16)
    return result.get("text", "").strip()
