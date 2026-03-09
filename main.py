import os
import uuid
import json
import shutil
import datetime
from typing import Optional, Dict, Any
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from openai import OpenAI
from dotenv import load_dotenv
import whisper

from detect_fracture import predict_fracture
from ocr import perform_ocr
from mtest_data_parser import extract_text_from_json
from json_builder import extract_prescription_data
from pdf_builder import build_pdf
from stt import speech_to_text_from_bytes
from tts import text_to_speech_file

load_dotenv()

# ---------- Configuration ----------
API_KEY = os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL")
MODEL = os.getenv("LLM_MODEL")
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", 10000))
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.3))

# Directories for temporary files
UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("output")
PDF_DIR = Path("pdfs")
for d in [UPLOAD_DIR, OUTPUT_DIR, PDF_DIR]:
    d.mkdir(exist_ok=True)

# ---------- Global Models ----------
openai_client = None
whisper_model = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global openai_client, whisper_model
    openai_client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    whisper_model = whisper.load_model("medium")
    print("Models loaded")
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Session Management ----------
sessions: Dict[str, Dict[str, Any]] = {}


def get_session(session_id: str) -> Dict[str, Any]:
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return sessions[session_id]


# ---------- Pydantic Models ----------
class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    session_id: str
    message: str
    phase: str
    prescription_ready: bool = False


# ---------- Helper Functions ----------
def ask_ai(messages):
    response = openai_client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
    )
    return response.choices[0].message.content


def generate_follow_up_questions(session):
    messages = session["messages"] + [
        {
            "role": "system",
            "content": (
                "You are a professional AI doctor. Based on the patient's symptom, "
                "generate 7-10 follow-up questions to better understand the condition. "
                "Return only the questions, one per line, ending with a question mark."
            ),
        }
    ]
    response = ask_ai(messages)
    questions = [q.strip() + "?" for q in response.split("?") if q.strip()]
    return questions


def generate_final_prescription(session):
    patient = session["patient"]
    today = datetime.date.today().strftime("%B %d, %Y")

    qna = "\n".join(
        [
            f"Q: {session['questions'][i]} A: {session['answers'][i]}"
            for i in range(len(session["answers"]))
        ]
    )

    messages = session["messages"] + [{"role": "user", "content": qna}]

    if session.get("xray_result"):
        messages.append(
            {"role": "system", "content": f"X-ray analysis: {session['xray_result']}"}
        )
    if session.get("ocr_result"):
        messages.append(
            {"role": "system", "content": f"Lab report OCR: {session['ocr_result']}"}
        )

    prompt = f"""
Based on all information above, generate a complete medical prescription in the following format. Be professional, use generic medication names when possible.

**Medical Prescription**

**Patient Information**: {patient['name']}, {patient['age']} years old, Gender: {patient['gender']}
**Date**: {today}

**Diagnosis**: [Insert accurate diagnosis]

**Medication**:
- **Name**: [Generic Name]
- **Dosage and Route**: [e.g., 500mg orally]
- **Frequency and Duration**: [e.g., Twice a day for 5 days]
- **Refills**: [e.g., None / 1 refill]
- **Special Instructions**: [e.g., Take with food]

**Non-Pharmacological Recommendations**

**Medical Tests Recommended**

**Reasoning**: [Brief reasoning for diagnosis and medication]

**Prescriber**: Dr. AI Medic. MD
---
"""
    messages.append({"role": "user", "content": prompt})
    full_response = ask_ai(messages)

    reasoning_start = full_response.find("**Reasoning**:")
    reasoning_end = full_response.find("**Prescriber**")
    reasoning = (
        full_response[reasoning_start + 14 : reasoning_end].strip()
        if reasoning_start != -1
        else ""
    )

    prescription_data = extract_prescription_data(full_response)
    session["prescription_data"] = prescription_data
    session["prescription_full"] = full_response
    session["reasoning"] = reasoning

    json_path = str(PDF_DIR / f"{session['session_id']}.json")
    with open(json_path, "w") as f:
        json.dump(prescription_data, f, indent=2)

    pdf_path = build_pdf(json_path, output_dir=str(PDF_DIR), filename=f"{session['session_id']}.pdf")
    session["pdf_path"] = pdf_path

    return full_response


# ---------- API Endpoints ----------
@app.post("/api/start-consultation")
async def start_consultation(
    name: str = Form(...),
    age: int = Form(...),
    gender: str = Form(...),
    xray: Optional[UploadFile] = File(None),
    report: Optional[UploadFile] = File(None),
):
    session_id = str(uuid.uuid4())
    session = {
        "session_id": session_id,
        "patient": {"name": name, "age": age, "gender": gender},
        "phase": "awaiting_symptom",
        "messages": [
            {"role": "system", "content": f"Patient: {name}, {age} years, {gender}"}
        ],
        "xray_result": None,
        "ocr_result": None,
        "questions": [],
        "answers": [],
        "question_index": 0,
        "prescription_data": None,
        "pdf_path": None,
        "reasoning": None,
    }
    sessions[session_id] = session

    if xray:
        xray_path = UPLOAD_DIR / f"{session_id}_xray.jpg"
        with open(xray_path, "wb") as f:
            shutil.copyfileobj(xray.file, f)
        fracture_result = predict_fracture(str(xray_path))
        session["xray_result"] = fracture_result
        session["messages"].append(
            {"role": "system", "content": f"X-ray analysis: {fracture_result}"}
        )

    if report:
        suffix = Path(report.filename).suffix if report.filename else ".png"
        report_path = UPLOAD_DIR / f"{session_id}_report{suffix}"
        with open(report_path, "wb") as f:
            shutil.copyfileobj(report.file, f)
        if suffix.lower() == ".json":
            ocr_text = extract_text_from_json(str(report_path))
        else:
            perform_ocr(str(report_path))
            json_output = OUTPUT_DIR / "large_res.json"
            if json_output.exists():
                ocr_text = extract_text_from_json(str(json_output))
            else:
                ocr_text = "[OCR failed]"
        session["ocr_result"] = ocr_text
        session["messages"].append(
            {"role": "system", "content": f"Lab report OCR: {ocr_text}"}
        )

    welcome = f"Welcome, {name}. Please describe your symptoms in detail."
    return {"session_id": session_id, "message": welcome, "phase": session["phase"]}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    session = get_session(req.session_id)
    user_msg = req.message.strip()

    session["messages"].append({"role": "user", "content": user_msg})

    if session["phase"] == "awaiting_symptom":
        session["phase"] = "questioning"
        session["messages"].append({"role": "user", "content": f"Symptom: {user_msg}"})
        questions = generate_follow_up_questions(session)
        session["questions"] = questions
        session["question_index"] = 0
        ai_msg = questions[0] if questions else "Please describe your symptoms further."
        session["messages"].append({"role": "assistant", "content": ai_msg})
        return ChatResponse(
            session_id=req.session_id, message=ai_msg, phase=session["phase"]
        )

    elif session["phase"] == "questioning":
        session["answers"].append(user_msg)
        idx = session["question_index"] + 1
        if idx < len(session["questions"]):
            session["question_index"] = idx
            ai_msg = session["questions"][idx]
            session["messages"].append({"role": "assistant", "content": ai_msg})
            return ChatResponse(
                session_id=req.session_id, message=ai_msg, phase=session["phase"]
            )
        else:
            session["phase"] = "generating"
            full_prescription = generate_final_prescription(session)
            session["phase"] = "complete"
            session["messages"].append(
                {"role": "assistant", "content": full_prescription}
            )
            return ChatResponse(
                session_id=req.session_id,
                message=full_prescription,
                phase="complete",
                prescription_ready=True,
            )

    elif session["phase"] == "complete":
        return ChatResponse(
            session_id=req.session_id,
            message="Consultation is complete. You can download the prescription.",
            phase="complete",
            prescription_ready=True,
        )

    else:
        raise HTTPException(status_code=400, detail="Invalid phase")


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
    text = speech_to_text_from_bytes(audio_bytes, whisper_model)
    return {"text": text}


@app.post("/api/tts")
async def tts_endpoint(background_tasks: BackgroundTasks, text: str = Form(...)):
    """Convert text to speech and return the MP3 file."""
    audio_path = text_to_speech_file(text)
    background_tasks.add_task(os.unlink, audio_path)
    return FileResponse(audio_path, media_type="audio/mpeg", filename="speech.mp3")


# IMPORTANT: Mount static files LAST so /api/* routes are matched first
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
