"""Media endpoints: voice transcription (Whisper) and text-to-speech (gTTS)."""

import asyncio
import os

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.logging import get_logger
from app.services import stt, tts

logger = get_logger("AIDoctor.API.Media")

router = APIRouter(prefix="/api", tags=["media"])


@router.post("/voice-input")
async def voice_input(audio: UploadFile = File(...)):
    """Transcribe uploaded audio using Whisper (requires ENABLE_VOICE)."""
    if not stt.is_available():
        raise HTTPException(status_code=503, detail="Voice transcription is not enabled on this server.")
    audio_bytes = await audio.read()
    if len(audio_bytes) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Audio file too large")
    text = await asyncio.to_thread(stt.transcribe, audio_bytes)
    return {"text": text}


@router.post("/tts")
async def tts_endpoint(background_tasks: BackgroundTasks, text: str = Form(..., max_length=5000)):
    """Convert text to speech and return an MP3."""
    try:
        audio_path = await asyncio.to_thread(tts.text_to_speech_file, text)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    background_tasks.add_task(os.unlink, audio_path)
    return FileResponse(audio_path, media_type="audio/mpeg", filename="speech.mp3")
