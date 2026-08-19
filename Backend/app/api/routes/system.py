"""System endpoints: root, health, and capabilities."""

from fastapi import APIRouter

from app.core.config import settings
from app.services import fracture, ocr, stt

router = APIRouter(tags=["system"])


@router.get("/")
async def root():
    return {"name": settings.APP_NAME, "version": settings.APP_VERSION, "docs": "/docs", "health": "/health"}


@router.get("/health")
async def health():
    return {
        "status": "healthy",
        "features": {
            "fracture_detection": fracture.is_available(),
            "ocr": ocr.is_available(),
            "voice": stt.is_available(),
        },
    }
