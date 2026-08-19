"""Consultation endpoints: start, chat, and prescription download."""

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import get_consultation
from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import ChatRequest, ChatResponse, StartConsultationResponse
from app.services import fracture, ocr
from app.services.consultation import ConsultationService

logger = get_logger("AIDoctor.API.Consultation")

router = APIRouter(prefix="/api", tags=["consultation"])

_ALLOWED_REPORT_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".json"}


@router.post("/start-consultation", response_model=StartConsultationResponse)
async def start_consultation(
    svc: ConsultationService = Depends(get_consultation),
    name: str = Form(..., min_length=1, max_length=100),
    age: int = Form(..., ge=0, le=120),
    gender: str = Form(...),
    xray: Optional[UploadFile] = File(None),
    report: Optional[UploadFile] = File(None),
):
    session = svc.create_session(name, age, gender)
    session_id = session["session_id"]

    if xray:
        xray_bytes = await xray.read()
        if len(xray_bytes) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="X-ray file too large")
        if fracture.is_available():
            xray_path = settings.upload_dir / f"{session_id}_xray.jpg"
            xray_path.write_bytes(xray_bytes)
            result = await asyncio.to_thread(fracture.predict_fracture, str(xray_path))
            session["xray_result"] = result.get("summary", str(result))
        else:
            session["xray_result"] = "X-ray analysis is not enabled on this server."

    if report:
        report_bytes = await report.read()
        if len(report_bytes) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="Report file too large")
        suffix = (Path(report.filename).suffix if report.filename else ".png").lower()
        if suffix not in _ALLOWED_REPORT_SUFFIXES:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
        report_path = settings.upload_dir / f"{session_id}_report{suffix}"
        report_path.write_bytes(report_bytes)

        if suffix == ".json":
            session["ocr_result"] = await asyncio.to_thread(ocr.extract_text_from_json, str(report_path))
        elif ocr.is_available():
            session_ocr_dir = settings.output_dir / session_id
            session_ocr_dir.mkdir(parents=True, exist_ok=True)
            json_output = await asyncio.to_thread(ocr.perform_ocr, str(report_path), str(session_ocr_dir))
            if json_output and Path(json_output).exists():
                session["ocr_result"] = await asyncio.to_thread(ocr.extract_text_from_json, json_output)
            else:
                session["ocr_result"] = "[OCR processing failed]"
        else:
            session["ocr_result"] = "Lab-report OCR is not enabled on this server."

    return StartConsultationResponse(
        session_id=session_id,
        message=f"Welcome, {name}. Please describe your symptoms in detail.",
        phase=session["phase"],
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, svc: ConsultationService = Depends(get_consultation)):
    session = svc.get_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    user_msg = req.message.strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if session["phase"] == "awaiting_symptom":
        session["phase"] = "questioning"
        session["initial_symptom"] = user_msg
        question = await svc.generate_next_question(session)
        session["questions"].append(question)
        return ChatResponse(session_id=req.session_id, message=question, phase=session["phase"])

    if session["phase"] == "questioning":
        session["answers"].append(user_msg)
        if len(session["answers"]) >= session["max_questions"]:
            session["phase"] = "generating"
            await svc.generate_prescription(session)
            session["phase"] = "complete"
            return ChatResponse(
                session_id=req.session_id,
                message="Your consultation is complete. Your prescription has been generated.",
                phase="complete", prescription_ready=True,
                prescription=session.get("prescription_data"),
            )
        question = await svc.generate_next_question(session)
        session["questions"].append(question)
        return ChatResponse(session_id=req.session_id, message=question, phase=session["phase"])

    if session["phase"] == "complete":
        return ChatResponse(
            session_id=req.session_id,
            message="Consultation is complete. You can download the prescription.",
            phase="complete", prescription_ready=True,
            prescription=session.get("prescription_data"),
        )

    raise HTTPException(status_code=400, detail="Invalid session phase")


@router.get("/prescription/{session_id}")
async def get_prescription(session_id: str, svc: ConsultationService = Depends(get_consultation)):
    session = svc.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    pdf_path = session.get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="Prescription not ready")
    return FileResponse(pdf_path, media_type="application/pdf", filename="prescription.pdf")
