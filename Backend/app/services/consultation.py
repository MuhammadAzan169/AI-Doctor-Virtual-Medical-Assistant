"""Consultation orchestration: session lifecycle, adaptive questioning, prescription.

In-memory sessions with TTL cleanup. For multi-instance deployments this should
be backed by a shared store (Redis); documented as a known limitation.
"""

import asyncio
import datetime
import json
import re
import shutil
import uuid
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.services.llm import SYSTEM_PROMPT, LLMClient
from app.services.pdf import build_pdf
from app.services.prescription_parser import extract_prescription_data, parse_structured_json

logger = get_logger("AIDoctor.Consultation")


def _parse_json_object(raw: str) -> dict | None:
    """Parse a bare JSON object from an LLM reply.

    prescription_parser.parse_structured_json is not usable here: it enforces
    the prescription schema and returns None for any other shape.
    """
    text = (raw or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            return None
    return data if isinstance(data, dict) else None


class ConsultationService:
    """Manages consultation sessions and the LLM-driven clinical flow."""

    def __init__(self) -> None:
        self.llm = LLMClient()
        self.sessions: Dict[str, Dict[str, Any]] = {}
        for d in (settings.upload_dir, settings.output_dir, settings.pdf_dir):
            d.mkdir(parents=True, exist_ok=True)

    # ── Session lifecycle ──────────────────────────────────────────────────
    def create_session(self, name: str, age: int, gender: str, context: str = "") -> Dict[str, Any]:
        self.cleanup_expired()
        session_id = str(uuid.uuid4())
        session = {
            "session_id": session_id,
            "patient": {"name": name.strip(), "age": age, "gender": gender.strip()},
            # Free-text background the patient supplied on the intake form.
            "context": (context or "").strip(),
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
        if session.get("context"):
            messages.append({"role": "system", "content": (
                f"Background provided by the patient: {session['context']}"
            )})
        if session.get("xray_result"):
            messages.append({"role": "system", "content": f"X-ray analysis: {session['xray_result']}"})
        if session.get("ocr_result"):
            messages.append({"role": "system", "content": f"Lab report: {session['ocr_result']}"})
        return messages

    async def summarize_lab_report(self, report_text: str) -> dict:
        """Pull the out-of-range results out of an extracted lab report.

        Returns {"summary": str, "items": [{label, value, reference, flag}]}.
        Structured rather than prose so the UI can present a real result table;
        never raises, because a summary failing must not fail the consultation.
        """
        excerpt = (report_text or "").strip()
        if not excerpt:
            return {"summary": "No readable text could be extracted from this report.", "items": []}
        # Keep the prompt bounded; abnormal values sit near the top of a report.
        excerpt = excerpt[:4000]

        task = (
            "Below is the text of a laboratory report. List every result that is "
            "outside its reference range.\n\n"
            "Output JSON only, in this shape:\n"
            '{"summary": "one short sentence naming the overall pattern", '
            '"items": [{"label": "Haemoglobin", "value": "11.2 g/dL", '
            '"reference": "13.0 - 17.0", "flag": "low"}]}\n\n'
            'flag must be exactly "high" or "low". Include at most 8 items. '
            "If every result is within range, return an empty items list and say so "
            "in the summary. Give no diagnosis and no advice.\n\n"
            "Report text:\n" + excerpt
        )
        messages = [
            {"role": "system", "content": "You extract laboratory values. You output JSON only."},
            {"role": "user", "content": task},
        ]

        # One retry: this call sits alongside the X-ray analysis on the same
        # request, and a transient empty completion would otherwise silently
        # downgrade the report to a bare acknowledgement.
        data = None
        for attempt in (1, 2):
            try:
                raw = await asyncio.to_thread(self.llm.ask_json, messages)
                data = _parse_json_object(raw)
            except Exception:
                logger.exception("Lab-report summary call failed (attempt %d)", attempt)
                data = None
            if isinstance(data, dict):
                break
            logger.warning("Lab-report summary unusable on attempt %d", attempt)

        if not isinstance(data, dict):
            return {"summary": "Report received and will be taken into account.", "items": []}

        items = []
        for raw in (data.get("items") or [])[:8]:
            if not isinstance(raw, dict):
                continue
            label = str(raw.get("label") or "").strip()
            value = str(raw.get("value") or "").strip()
            if not label or not value:
                continue
            flag = str(raw.get("flag") or "").strip().lower()
            items.append({
                "label": label,
                "value": value,
                "reference": str(raw.get("reference") or "").strip(),
                "flag": flag if flag in ("high", "low") else "",
            })

        summary = str(data.get("summary") or "").strip()
        if not summary:
            summary = (
                "%d result(s) fall outside their reference range." % len(items)
                if items else "All results are within their reference ranges."
            )
        return {"summary": summary, "items": items}

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

    async def handle_patient_reply(self, session: dict, user_msg: str) -> tuple[bool, str]:
        """Decide whether the patient answered the pending question, and reply.

        Returns (is_answer, message). A patient who says "what?", "hello", or
        asks a question of their own has not answered anything — recording that
        as an answer corrupts the history the prescription is built from, and
        moving straight to the next question makes the assistant look deaf.

        One LLM call covers both branches, so an ordinary answer costs no more
        than it did before. The task goes in a *user* message: the models we
        use return an empty completion when a long instruction like this is
        sent as a trailing system message.
        """
        pending = session["questions"][-1] if session["questions"] else ""
        qna = "".join(
            "Q: %s\nA: %s\n" % (session["questions"][i], session["answers"][i])
            for i in range(len(session["answers"]))
        )

        asked = len(session["answers"])
        remaining = session["max_questions"] - asked
        task = (
            "Decide whether the patient answered the question.\n\n"
            "Question asked: %s\n"
            "Patient reply: %s\n\n"
            "A reply does NOT answer the question if the patient asks you anything "
            "(including why you are asking, or what you meant), says they do not "
            "understand, greets you, asks if you are there, or says you ignored "
            "them. Saying they do not know, or that a symptom is absent, DOES "
            "answer it. A reply that answers only part of the question still "
            "counts as an answer.\n\n"
            "If it answers, output: "
            '{"is_answer": true, "next_question": "one new follow-up question"}\n'
            "If it does not, output: "
            '{"is_answer": false, "reply": "respond to what they said, then ask '
            'the same question again in simpler words"}\n\n'
            "Patient: %s, %s years old, %s. Reported symptoms: %s\n"
            "%s"
            "You have asked %d follow-up questions and have %d remaining. Any "
            "next_question must differ from every question already asked."
        ) % (
            pending,
            user_msg,
            session["patient"]["name"],
            session["patient"]["age"],
            session["patient"]["gender"],
            session["initial_symptom"],
            ("Previous Q&A:\n" + qna) if qna else "",
            asked,
            remaining,
        )

        messages = [
            {"role": "system", "content": "You are a physician assistant. You output JSON only."},
            {"role": "user", "content": task},
        ]

        try:
            raw = await asyncio.to_thread(self.llm.ask_json, messages)
            data = _parse_json_object(raw)
        except Exception:
            logger.exception("Classifying the patient reply failed")
            data = None

        if not isinstance(data, dict) or "is_answer" not in data:
            # Unparseable: treat it as an answer so the consultation still moves
            # forward rather than trapping the patient in a loop.
            logger.warning("Could not classify patient reply — treating it as an answer.")
            return True, await self.generate_next_question(session)

        if data.get("is_answer"):
            question = str(data.get("next_question") or "").strip()
            if not question:
                question = await self.generate_next_question(session)
            if not question.endswith("?"):
                question += "?"
            return True, question

        reply = str(data.get("reply") or "").strip()
        if not reply:
            reply = "Sorry — let me put that differently. " + pending
        return False, reply

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
