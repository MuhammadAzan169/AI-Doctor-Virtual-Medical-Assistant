"""Pydantic request/response models."""

from typing import Dict, Optional

from pydantic import BaseModel, Field

from app.core.config import settings


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., max_length=settings.MAX_MESSAGE_LENGTH)


class ChatResponse(BaseModel):
    session_id: str
    message: str
    phase: str
    prescription_ready: bool = False
    prescription: Optional[Dict] = None


class StartConsultationResponse(BaseModel):
    session_id: str
    message: str
    phase: str
