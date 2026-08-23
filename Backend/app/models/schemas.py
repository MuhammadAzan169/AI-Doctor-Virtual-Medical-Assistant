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


class FindingItem(BaseModel):
    """One measured value within a finding."""
    label: str
    value: str
    reference: str = ""
    # "high" | "low" | "" — drives the badge shown next to the value.
    flag: str = ""


class Finding(BaseModel):
    """A structured result from one uploaded attachment."""
    # "xray" | "lab" — selects the icon and accent in the UI.
    kind: str
    title: str
    summary: str = ""
    items: list[FindingItem] = []
    note: str = ""


class StartConsultationResponse(BaseModel):
    session_id: str
    message: str
    phase: str
    # What the uploaded X-ray and lab report actually showed, so the patient
    # sees the findings instead of the assistant using them silently.
    findings: list[Finding] = []
