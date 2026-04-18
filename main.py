import os
import uuid
import json
import time
import shutil
import asyncio
import datetime
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware

from openai import OpenAI
from dotenv import load_dotenv

from detect_fracture import predict_fracture
from ocr import perform_ocr
from mtest_data_parser import extract_text_from_json
from json_builder import extract_prescription_data, PRESCRIPTION_JSON_SCHEMA
from pdf_builder import build_pdf
from stt import speech_to_text_from_bytes
from tts import text_to_speech_file

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ---------- Configuration ----------
BASE_URL = os.getenv("LLM_BASE_URL")
MODEL = os.getenv("LLM_MODEL")
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", 10000))
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.3))
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",") or ["*"]

# Collect all available API keys (LLM_API_KEY + OPENROUTER_API_KEY1..N)
_raw_keys: list[str] = []
for _k in ["LLM_API_KEY"] + [f"OPENROUTER_API_KEY{i}" for i in range(1, 20)]:
    _v = os.getenv(_k)
    if _v and _v not in _raw_keys:
        _raw_keys.append(_v)
API_KEYS: list[str] = _raw_keys
API_KEY = API_KEYS[0] if API_KEYS else None
_current_key_index = 0

# Limits
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_MESSAGE_LENGTH = 5000
SESSION_TTL_SECONDS = 3600  # 1 hour

# Directories
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("output")
PDF_DIR = Path("pdfs")
for d in [UPLOAD_DIR, OUTPUT_DIR, PDF_DIR]:
    d.mkdir(exist_ok=True)

# ---------- Global Models ----------
openai_client: Optional[OpenAI] = None
whisper_model = None

# ---------- System Prompt ----------
SYSTEM_PROMPT = """You are a board-certified virtual physician assistant (AI Doctor).
You follow evidence-based clinical guidelines and practice safe, conservative medicine.

Rules:
- Ask clear, targeted follow-up questions to narrow down the diagnosis.
- Never make definitive diagnoses for serious conditions without sufficient information.
- Always recommend in-person follow-up for any concerning symptoms.
- Use generic medication names when possible.
- Consider patient age, gender, and any provided lab/imaging results.
- Be empathetic but professional.
- If you detect potentially dangerous symptoms (chest pain, difficulty breathing, etc.), advise the patient to seek emergency care immediately.
- Do NOT prescribe controlled substances.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    global openai_client, whisper_model
    openai_client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    logger.info("OpenAI client initialized with %d API key(s). Whisper will load on first voice request.", len(API_KEYS))
    yield
    # Cleanup sessions and temp files
    _cleanup_all_sessions()


app = FastAPI(lifespan=lifespan)


# ---------- Request Logging Middleware ----------
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        method = request.method
        path = request.url.path
        logger.info(">>> %s %s", method, path)
        try:
            response = await call_next(request)
            elapsed = (time.perf_counter() - start) * 1000
            logger.info(
                "<<< %s %s -> %d (%.1fms)",
                method, path, response.status_code, elapsed,
            )
            return response
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                "<<< %s %s -> EXCEPTION (%.1fms): %s",
                method, path, elapsed, exc,
            )
            raise


app.add_middleware(RequestLoggingMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Session Management ----------
sessions: Dict[str, Dict[str, Any]] = {}


def _get_whisper():
    """Lazily load whisper model on first use."""
    global whisper_model
    if whisper_model is None:
        import whisper
        logger.info("Loading Whisper model...")
        whisper_model = whisper.load_model("medium")
        logger.info("Whisper model loaded.")
    return whisper_model


def get_session(session_id: str) -> Dict[str, Any]:
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = sessions[session_id]
    # Update last-accessed timestamp
    session["last_accessed"] = datetime.datetime.utcnow()
    return session


def _cleanup_expired_sessions():
    """Remove sessions older than TTL and their uploaded files."""
    now = datetime.datetime.utcnow()
    expired = [
        sid for sid, s in sessions.items()
        if (now - s.get("last_accessed", now)).total_seconds() > SESSION_TTL_SECONDS
    ]
    for sid in expired:
        _cleanup_session(sid)


def _cleanup_session(session_id: str):
    """Remove a single session's temp files and data."""
    session = sessions.pop(session_id, None)
    if not session:
        return
    # Clean up uploaded files
    for pattern in [f"{session_id}_*"]:
        for f in UPLOAD_DIR.glob(pattern):
            f.unlink(missing_ok=True)
    # Clean up session-specific OCR output
    ocr_dir = OUTPUT_DIR / session_id
    if ocr_dir.exists():
        shutil.rmtree(ocr_dir, ignore_errors=True)
    # Clean up PDFs
    for ext in [".json", ".pdf"]:
        p = PDF_DIR / f"{session_id}{ext}"
        p.unlink(missing_ok=True)


def _cleanup_all_sessions():
    for sid in list(sessions.keys()):
        _cleanup_session(sid)


# ---------- Pydantic Models ----------
class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., max_length=MAX_MESSAGE_LENGTH)


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


# ---------- LLM Helpers ----------
from openai import AuthenticationError as _OAIAuthError
from openai import RateLimitError as _OAIRateLimitError
from openai import InternalServerError as _OAIServerError


def _rotate_key() -> bool:
    """Switch to the next available API key. Returns True if a new key was selected."""
    global openai_client, _current_key_index
    next_idx = _current_key_index + 1
    if next_idx >= len(API_KEYS):
        logger.error("All %d API keys exhausted.", len(API_KEYS))
        return False
    _current_key_index = next_idx
    openai_client = OpenAI(base_url=BASE_URL, api_key=API_KEYS[_current_key_index])
    logger.warning("Key %d failed, rotating to key %d of %d.", _current_key_index, _current_key_index + 1, len(API_KEYS))
    return True


def _reset_key_index():
    """Reset to the first key at the start of each user request."""
    global openai_client, _current_key_index
    if _current_key_index != 0:
        _current_key_index = 0
        openai_client = OpenAI(base_url=BASE_URL, api_key=API_KEYS[0])


def _normalize_messages(messages: list) -> list:
    """Convert system messages to user messages for models that don't support them."""
    normalized = []
    system_parts = []
    for msg in messages:
        if msg["role"] == "system":
            system_parts.append(msg["content"])
        else:
            if system_parts:
                # Prepend accumulated system content as a user message
                normalized.append({"role": "user", "content": "[Instructions]\n" + "\n\n".join(system_parts)})
                normalized.append({"role": "assistant", "content": "Understood. I will follow these instructions."})
                system_parts = []
            normalized.append(msg)
    # If trailing system messages exist
    if system_parts:
        normalized.append({"role": "user", "content": "[Instructions]\n" + "\n\n".join(system_parts)})
        normalized.append({"role": "assistant", "content": "Understood."})
    return normalized


def _ask_ai(messages: list, temperature: float = TEMPERATURE, max_tokens: int = MAX_TOKENS) -> str:
    """Send messages to the LLM and return the response text. Rotates keys on 401/429/503."""
    _reset_key_index()
    normalized = _normalize_messages(messages)
    while True:
        try:
            logger.info(
                "LLM REQUEST -> POST %s model=%s key=%d/%d tokens=%d temp=%.2f",
                BASE_URL, MODEL, _current_key_index + 1, len(API_KEYS), max_tokens, temperature,
            )
            start = time.perf_counter()
            response = openai_client.chat.completions.create(
                model=MODEL,
                messages=normalized,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            elapsed = (time.perf_counter() - start) * 1000
            content = response.choices[0].message.content
            logger.info(
                "LLM RESPONSE <- 200 OK (%.1fms) chars=%d key=%d/%d",
                elapsed, len(content) if content else 0, _current_key_index + 1, len(API_KEYS),
            )
            return content
        except (_OAIAuthError, _OAIRateLimitError, _OAIServerError) as e:
            logger.warning("LLM RESPONSE <- %s key=%d/%d", e, _current_key_index + 1, len(API_KEYS))
            if not _rotate_key():
                raise


def _ask_ai_json(messages: list, temperature: float = 0.1, max_tokens: int = MAX_TOKENS) -> str:
    """Send messages to the LLM requesting JSON output. Rotates keys on 401/429/503."""
    _reset_key_index()
    normalized = _normalize_messages(messages)
    while True:
        try:
            logger.info(
                "LLM REQUEST (JSON) -> POST %s model=%s key=%d/%d",
                BASE_URL, MODEL, _current_key_index + 1, len(API_KEYS),
            )
            start = time.perf_counter()
            response = openai_client.chat.completions.create(
                model=MODEL,
                messages=normalized,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            elapsed = (time.perf_counter() - start) * 1000
            content = response.choices[0].message.content
            logger.info(
                "LLM RESPONSE (JSON) <- 200 OK (%.1fms) chars=%d key=%d/%d",
                elapsed, len(content) if content else 0, _current_key_index + 1, len(API_KEYS),
            )
            return content
        except (_OAIAuthError, _OAIRateLimitError, _OAIServerError) as e:
            logger.warning("LLM RESPONSE (JSON) <- %s key=%d/%d", e, _current_key_index + 1, len(API_KEYS))
            if not _rotate_key():
                raise
        except Exception:
            # Fallback: some providers don't support response_format
            logger.warning("JSON mode not supported, falling back to plain text.")
            return _ask_ai(messages, temperature=temperature, max_tokens=max_tokens)


async def _ask_ai_async(messages: list, **kwargs) -> str:
    """Run LLM call in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(_ask_ai, messages, **kwargs)


async def _ask_ai_json_async(messages: list, **kwargs) -> str:
    """Run JSON LLM call in a thread."""
    return await asyncio.to_thread(_ask_ai_json, messages, **kwargs)


# ---------- Adaptive Follow-up Question Generation ----------
async def generate_next_question(session: dict) -> str:
    """
    Generate the next follow-up question adaptively based on all
    previously gathered information (symptoms + prior Q&A).
    """
    qna_so_far = ""
    for i in range(len(session["answers"])):
        qna_so_far += f"Q: {session['questions'][i]}\nA: {session['answers'][i]}\n"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                f"Patient: {session['patient']['name']}, "
                f"{session['patient']['age']} years old, "
                f"Gender: {session['patient']['gender']}"
            ),
        },
    ]

    if session.get("xray_result"):
        messages.append(
            {"role": "system", "content": f"X-ray analysis: {session['xray_result']}"}
        )
    if session.get("ocr_result"):
        messages.append(
            {"role": "system", "content": f"Lab report: {session['ocr_result']}"}
        )

    messages.append(
        {"role": "user", "content": f"My symptoms: {session['initial_symptom']}"}
    )

    if qna_so_far:
        messages.append(
            {"role": "assistant", "content": f"Previous follow-up Q&A:\n{qna_so_far}"}
        )

    questions_asked = len(session["answers"])
    remaining = session["max_questions"] - questions_asked

    messages.append({
        "role": "system",
        "content": (
            f"You have asked {questions_asked} follow-up questions so far. "
            f"You have {remaining} questions remaining. "
            "Generate exactly ONE next follow-up question to better understand "
            "the patient's condition. The question should be different from "
            "all previously asked questions. Return ONLY the question, nothing else."
        ),
    })

    response = await _ask_ai_async(messages)
    question = response.strip().split("\n")[0].strip()
    if not question.endswith("?"):
        question += "?"
    return question


# ---------- Prescription Generation ----------
async def generate_final_prescription(session: dict) -> str:
    """Generate the final prescription using structured JSON output."""
    patient = session["patient"]
    today = datetime.date.today().strftime("%B %d, %Y")

    qna = "\n".join(
        f"Q: {session['questions'][i]} A: {session['answers'][i]}"
        for i in range(len(session["answers"]))
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                f"Patient: {patient['name']}, {patient['age']} years old, "
                f"Gender: {patient['gender']}"
            ),
        },
    ]

    if session.get("xray_result"):
        messages.append(
            {"role": "system", "content": f"X-ray analysis: {session['xray_result']}"}
        )
    if session.get("ocr_result"):
        messages.append(
            {"role": "system", "content": f"Lab report: {session['ocr_result']}"}
        )

    messages.append({"role": "user", "content": f"Symptoms: {session['initial_symptom']}"})
    messages.append({"role": "assistant", "content": f"Follow-up Q&A:\n{qna}"})

    # Request structured JSON prescription
    messages.append({
        "role": "user",
        "content": f"""Based on all information above, generate a complete medical prescription as a JSON object with this exact structure:

{{
  "patient_info": {{
    "name": "{patient['name']}",
    "age": {patient['age']},
    "gender": "{patient['gender']}",
    "date": "{today}"
  }},
  "diagnosis": "Your diagnosis here",
  "medication": [
    {{
      "name": "Generic medication name",
      "dosage_and_route": "e.g., 500mg orally",
      "frequency_and_duration": "e.g., Twice a day for 5 days",
      "refills": "e.g., None",
      "special_instructions": "e.g., Take with food"
    }}
  ],
  "non_pharmacological_recommendations": [
    {{
      "title": "Recommendation title",
      "details": {{"text": "Detailed recommendation"}}
    }}
  ],
  "medical_tests": [
    {{
      "test_name": "Test name",
      "details": {{"text": "Reason for test"}}
    }}
  ],
  "prescriber": {{
    "name": "Dr. AI Medic, MD"
  }},
  "reasoning": "Brief clinical reasoning for diagnosis and treatment plan"
}}

Rules:
- Use generic medication names when possible.
- Do NOT prescribe controlled substances.
- Be conservative and evidence-based.
- Always recommend in-person follow-up.
- Return ONLY valid JSON, no markdown or extra text.""",
    })

    full_response = await _ask_ai_json_async(messages, temperature=0.1)

    prescription_data = extract_prescription_data(full_response)
    session["prescription_data"] = prescription_data
    session["reasoning"] = prescription_data.get("reasoning", "")

    # Save JSON
    json_path = str(PDF_DIR / f"{session['session_id']}.json")
    with open(json_path, "w") as f:
        json.dump(prescription_data, f, indent=2)

    # Build PDF in thread
    pdf_path = await asyncio.to_thread(
        build_pdf, json_path, output_dir=str(PDF_DIR),
        filename=f"{session['session_id']}.pdf"
    )
    session["pdf_path"] = pdf_path

    return full_response


# ---------- API Endpoints ----------

@app.post("/api/start-consultation", response_model=StartConsultationResponse)
async def start_consultation(
    name: str = Form(..., min_length=1, max_length=100),
    age: int = Form(..., ge=0, le=120),
    gender: str = Form(...),
    xray: Optional[UploadFile] = File(None),
    report: Optional[UploadFile] = File(None),
):
    # Cleanup expired sessions periodically
    _cleanup_expired_sessions()

    session_id = str(uuid.uuid4())
    session = {
        "session_id": session_id,
        "patient": {"name": name.strip(), "age": age, "gender": gender.strip()},
        "phase": "awaiting_symptom",
        "initial_symptom": None,
        "xray_result": None,
        "ocr_result": None,
        "questions": [],
        "answers": [],
        "max_questions": 8,
        "prescription_data": None,
        "pdf_path": None,
        "reasoning": None,
        "last_accessed": datetime.datetime.utcnow(),
    }
    sessions[session_id] = session

    # Process X-ray upload
    if xray:
        xray_bytes = await xray.read()
        if len(xray_bytes) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="X-ray file too large (max 10MB)")
        xray_path = UPLOAD_DIR / f"{session_id}_xray.jpg"
        xray_path.write_bytes(xray_bytes)
        fracture_result = await asyncio.to_thread(predict_fracture, str(xray_path))
        session["xray_result"] = fracture_result.get("summary", str(fracture_result))

    # Process lab report upload
    if report:
        report_bytes = await report.read()
        if len(report_bytes) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="Report file too large (max 10MB)")
        suffix = Path(report.filename).suffix if report.filename else ".png"
        # Sanitize suffix
        allowed_suffixes = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".json"}
        if suffix.lower() not in allowed_suffixes:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
        report_path = UPLOAD_DIR / f"{session_id}_report{suffix}"
        report_path.write_bytes(report_bytes)

        if suffix.lower() == ".json":
            ocr_text = await asyncio.to_thread(extract_text_from_json, str(report_path))
        else:
            # Use session-specific output dir to avoid race conditions
            session_ocr_dir = OUTPUT_DIR / session_id
            session_ocr_dir.mkdir(exist_ok=True)
            json_output = await asyncio.to_thread(
                perform_ocr, str(report_path), str(session_ocr_dir)
            )
            if json_output and Path(json_output).exists():
                ocr_text = await asyncio.to_thread(extract_text_from_json, json_output)
            else:
                ocr_text = "[OCR processing failed]"

        session["ocr_result"] = ocr_text

    welcome = f"Welcome, {name}. Please describe your symptoms in detail."
    return StartConsultationResponse(
        session_id=session_id, message=welcome, phase=session["phase"]
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session = get_session(req.session_id)
    user_msg = req.message.strip()

    if not user_msg:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if session["phase"] == "awaiting_symptom":
        session["phase"] = "questioning"
        session["initial_symptom"] = user_msg

        # Generate first adaptive question
        first_question = await generate_next_question(session)
        session["questions"].append(first_question)

        return ChatResponse(
            session_id=req.session_id,
            message=first_question,
            phase=session["phase"],
        )

    elif session["phase"] == "questioning":
        session["answers"].append(user_msg)

        if len(session["answers"]) >= session["max_questions"]:
            # All questions answered — generate prescription
            session["phase"] = "generating"
            await generate_final_prescription(session)
            session["phase"] = "complete"

            return ChatResponse(
                session_id=req.session_id,
                message="Your consultation is complete. Your prescription has been generated.",
                phase="complete",
                prescription_ready=True,
                prescription=session.get("prescription_data"),
            )
        else:
            # Generate next adaptive question
            next_question = await generate_next_question(session)
            session["questions"].append(next_question)

            return ChatResponse(
                session_id=req.session_id,
                message=next_question,
                phase=session["phase"],
            )

    elif session["phase"] == "complete":
        return ChatResponse(
            session_id=req.session_id,
            message="Consultation is complete. You can download the prescription.",
            phase="complete",
            prescription_ready=True,
            prescription=session.get("prescription_data"),
        )

    else:
        raise HTTPException(status_code=400, detail="Invalid session phase")


@app.get("/api/prescription/{session_id}")
async def get_prescription(session_id: str):
    session = get_session(session_id)
    pdf_path = session.get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        raise HTTPException(status_code=404, detail="Prescription not ready")
    return FileResponse(
        pdf_path, media_type="application/pdf", filename="prescription.pdf"
    )


@app.post("/api/voice-input")
async def voice_input(audio: UploadFile = File(...)):
    """Transcribe uploaded audio using Whisper."""
    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Audio file too large (max 10MB)")
    model = _get_whisper()
    text = await asyncio.to_thread(speech_to_text_from_bytes, audio_bytes, model)
    return {"text": text}


@app.post("/api/tts")
async def tts_endpoint(
    background_tasks: BackgroundTasks,
    text: str = Form(..., max_length=5000),
):
    """Convert text to speech and return the MP3 file."""
    audio_path = await asyncio.to_thread(text_to_speech_file, text)
    background_tasks.add_task(os.unlink, audio_path)
    return FileResponse(audio_path, media_type="audio/mpeg", filename="speech.mp3")


# IMPORTANT: Mount static files LAST so /api/* routes are matched first
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
