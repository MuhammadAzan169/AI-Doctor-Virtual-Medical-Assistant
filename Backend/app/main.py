"""FastAPI entry point for the AI Doctor API.

Run locally:  uvicorn app.main:app --reload
Run for prod: uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import consultation, media, system
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.services.llm import LLMUnavailableError

logger = get_logger("AIDoctor.Server")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
            elapsed = (time.perf_counter() - start) * 1000
            logger.info("%s %s -> %d (%.1fms)", request.method, request.url.path, response.status_code, elapsed)
            return response
        except Exception as exc:
            logger.error("%s %s -> EXCEPTION: %s", request.method, request.url.path, exc)
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting AI Doctor API…")
    from app.services.consultation import ConsultationService

    app.state.consultation = ConsultationService()
    logger.info(
        "Features — fracture:%s ocr:%s voice:%s",
        settings.ENABLE_FRACTURE, settings.ENABLE_OCR, settings.ENABLE_VOICE,
    )
    yield
    app.state.consultation.cleanup_all()
    logger.info("🛑 Server shutting down")


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    @app.exception_handler(LLMUnavailableError)
    async def _llm_unavailable(request: Request, exc: LLMUnavailableError):
        """Surface LLM outages as a clean 503 the frontend can render."""
        logger.error("LLM unavailable on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=503,
            content={"detail": "The medical AI service is temporarily unavailable. Please try again shortly."},
        )

    app.include_router(system.router)
    app.include_router(consultation.router)
    app.include_router(media.router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=False)
