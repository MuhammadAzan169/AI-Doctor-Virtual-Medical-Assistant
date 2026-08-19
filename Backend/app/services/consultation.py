"""Consultation orchestration: session lifecycle, adaptive questioning, prescription.

In-memory sessions with TTL cleanup. For multi-instance deployments this should
be backed by a shared store (Redis); documented as a known limitation.
"""

import asyncio
import datetime
import json
import shutil
import uuid
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.services.llm import SYSTEM_PROMPT, LLMClient
from app.services.pdf import build_pdf
from app.services.prescription_parser import extract_prescription_data

logger = get_logger("AIDoctor.Consultation")


class ConsultationService:
    """Manages consultation sessions and the LLM-driven clinical flow."""

    def __init__(self) -> None:
        self.llm = LLMClient()
        self.sessions: Dict[str, Dict[str, Any]] = {}
        for d in (settings.upload_dir, settings.output_dir, settings.pdf_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ── Session lifecycle ──────────────────────────────────────────────────
    def create_session(self, name: str, age: int, gender: str) -> Dict[str, Any]:
        self.cleanup_expired()
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
            "max_questions": settings.MAX_QUESTIONS,
            "prescription_data": None,
            "pdf_path": None,
            "reasoning": None,
            "last_accessed": datetime.datetime.utcnow(),
        }
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self.sessions.get(session_id)
        if session:
            session["last_accessed"] = datetime.datetime.utcnow()
        return session

    def cleanup_expired(self) -> None:
        now = datetime.datetime.utcnow()
        expired = [
            sid for sid, s in self.sessions.items()
            if (now - s.get("last_accessed", now)).total_seconds() > settings.SESSION_TTL_SECONDS
        ]
        for sid in expired:
            self.cleanup_session(sid)

    def cleanup_session(self, session_id: str) -> None:
        if not self.sessions.pop(session_id, None):
            return
        for f in settings.upload_dir.glob(f"{session_id}_*"):
            f.unlink(missing_ok=True)
        ocr_dir = settings.output_dir / session_id
        if ocr_dir.exists():
            shutil.rmtree(ocr_dir, ignore_errors=True)
        for ext in (".json", ".pdf"):
            (settings.pdf_dir / f"{session_id}{ext}").unlink(missing_ok=True)

    def cleanup_all(self) -> None:
        for sid in list(self.sessions.keys()):
            self.cleanup_session(sid)

    # ── Clinical flow ──────────────────────────────────────────────────────
    def _base_messages(self, session: dict) -> list:
        patient = session["patient"]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": (
                f"Patient: {patient['name']}, {patient['age']} years old, Gender: {patient['gender']}"
            )},
        ]
        if session.get("xray_result"):
            messages.append({"role": "system", "content": f"X-ray analysis: {session['xray_result']}"})
        if session.get("ocr_result"):
            messages.append({"role": "system", "content": f"Lab report: {session['ocr_result']}"})
        return messages

    async def generate_next_question(self, session: dict) -> str:
        qna = "".join(
            f"Q: {session['questions'][i]}\nA: {session['answers'][i]}\n"
            for i in range(len(session["answers"]))
        )
        messages = self._base_messages(session)
        messages.append({"role": "user", "content": f"My symptoms: {session['initial_symptom']}"})
        if qna:
            messages.append({"role": "assistant", "content": f"Previous follow-up Q&A:\n{qna}"})

        asked = len(session["answers"])
        remaining = session["max_questions"] - asked
        messages.append({"role": "system", "content": (
            f"You have asked {asked} follow-up questions so far. You have {remaining} remaining. "
            "Generate exactly ONE next follow-up question to better understand the patient's "
            "condition, different from all previously asked questions. Return ONLY the question."
        )})

        response = await asyncio.to_thread(self.llm.ask, messages)
        question = response.strip().split("\n")[0].strip()
        if not question.endswith("?"):
            question += "?"
        return question

    async def generate_prescription(self, session: dict) -> Dict[str, Any]:
        patient = session["patient"]
        today = datetime.date.today().strftime("%B %d, %Y")
        qna = "\n".join(
            f"Q: {session['questions'][i]} A: {session['answers'][i]}"
            for i in range(len(session["answers"]))
        )
        messages = self._base_messages(session)
        messages.append({"role": "user", "content": f"Symptoms: {session['initial_symptom']}"})
        messages.append({"role": "assistant", "content": f"Follow-up Q&A:\n{qna}"})
        messages.append({"role": "user", "content": _PRESCRIPTION_PROMPT.format(
            name=patient["name"], age=patient["age"], gender=patient["gender"], date=today,
        )})

        raw = await asyncio.to_thread(self.llm.ask_json, messages, 0.1)
        prescription = extract_prescription_data(raw)
        session["prescription_data"] = prescription
        session["reasoning"] = prescription.get("reasoning", "")

        json_path = str(settings.pdf_dir / f"{session['session_id']}.json")
        with open(json_path, "w") as f:
            json.dump(prescription, f, indent=2)

        session["pdf_path"] = await asyncio.to_thread(
            build_pdf, json_path, str(settings.pdf_dir), f"{session['session_id']}.pdf"
        )
        return prescription


_PRESCRIPTION_PROMPT = """Based on all information above, generate a complete medical prescription as a JSON object with this exact structure:

{{
  "patient_info": {{ "name": "{name}", "age": {age}, "gender": "{gender}", "date": "{date}" }},
  "diagnosis": "Your diagnosis here",
  "medication": [
    {{ "name": "Generic medication name", "dosage_and_route": "e.g., 500mg orally", "frequency_and_duration": "e.g., Twice a day for 5 days", "refills": "e.g., None", "special_instructions": "e.g., Take with food" }}
  ],
  "non_pharmacological_recommendations": [ {{ "title": "Recommendation title", "details": {{"text": "Detailed recommendation"}} }} ],
  "medical_tests": [ {{ "test_name": "Test name", "details": {{"text": "Reason for test"}} }} ],
  "prescriber": {{ "name": "Dr. AI Medic, MD" }},
  "reasoning": "Brief clinical reasoning for diagnosis and treatment plan"
}}

Rules:
- Use generic medication names when possible.
- Do NOT prescribe controlled substances.
- Be conservative and evidence-based.
- Always recommend in-person follow-up.
- Return ONLY valid JSON, no markdown or extra text."""
