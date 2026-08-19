"""Shared API dependencies."""

from fastapi import HTTPException, Request

from app.services.consultation import ConsultationService


def get_consultation(request: Request) -> ConsultationService:
    svc = getattr(request.app.state, "consultation", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Service not available")
    return svc
