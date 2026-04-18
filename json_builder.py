import re
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# ---------- JSON Schema for structured LLM output ----------
PRESCRIPTION_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "patient_info": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "gender": {"type": "string"},
                "date": {"type": "string"},
            },
            "required": ["name", "age", "gender", "date"],
        },
        "diagnosis": {"type": "string"},
        "medication": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "dosage_and_route": {"type": "string"},
                    "frequency_and_duration": {"type": "string"},
                    "refills": {"type": "string"},
                    "special_instructions": {"type": "string"},
                },
                "required": ["name", "dosage_and_route", "frequency_and_duration"],
            },
        },
        "non_pharmacological_recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "details": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                    },
                },
                "required": ["title", "details"],
            },
        },
        "medical_tests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "test_name": {"type": "string"},
                    "details": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                    },
                },
                "required": ["test_name", "details"],
            },
        },
        "prescriber": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        },
        "reasoning": {"type": "string"},
    },
    "required": [
        "patient_info",
        "diagnosis",
        "medication",
        "non_pharmacological_recommendations",
        "medical_tests",
        "prescriber",
        "reasoning",
    ],
}


def parse_structured_json(raw_text: str) -> Dict | None:
    """
    Try to parse the LLM response as JSON directly.
    Returns a validated dict or *None* if parsing fails.
    """
    # Strip markdown code fences if present
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None

    # Quick structural validation
    required_keys = {"patient_info", "diagnosis", "medication"}
    if not required_keys.issubset(data.keys()):
        logger.warning("Structured JSON missing required keys: %s", required_keys - data.keys())
        return None

    # Ensure sub-fields have sane defaults
    pi = data.get("patient_info", {})
    pi.setdefault("name", "")
    pi.setdefault("age", 0)
    pi.setdefault("gender", "")
    pi.setdefault("date", "")
    if isinstance(pi.get("age"), str):
        try:
            pi["age"] = int(re.search(r"\d+", pi["age"]).group())
        except (AttributeError, ValueError):
            pi["age"] = 0

    data.setdefault("non_pharmacological_recommendations", [])
    data.setdefault("medical_tests", [])
    data.setdefault("prescriber", {"name": "Dr. AI Medic, MD"})
    data.setdefault("reasoning", "")

    return data


# ---------- Regex Fallback (legacy free-text parsing) ----------

def _extract_prescription_regex(text: str) -> Dict:
    """Extract structured prescription data from markdown-formatted text using regex."""

    def extract_field(pattern, source=None, default=""):
        src = source if source else text
        match = re.search(pattern, src, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else default

    def extract_medications(section: str) -> List[Dict]:
        if not section or "Not applicable" in section or "No medication prescribed" in section:
            return []

        meds = []
        # Split on numbered items or bullet items that precede a Name field
        med_blocks = re.split(
            r"(?:\n|^)\s*(?:\d+[\.\)]|\-|\*)\s*(?=\*\*Name\*\*:)",
            section.strip(),
        )

        for block in med_blocks:
            block = block.strip()
            if not block:
                continue
            if not block.startswith("**Name**:"):
                block = "**Name**: " + block

            raw_name = extract_field(r"\*\*Name\*\*:\s*(.+?)(\n|$)", block)
            cleaned_name = re.sub(r"^\d+[\.\)]\s*", "", raw_name).strip()
            dosage = extract_field(r"\*\*Dosage and Route\*\*:\s*(.+?)(\n|$)", block)
            freq = extract_field(r"\*\*Frequency and Duration\*\*:\s*(.+?)(\n|$)", block)
            refills = extract_field(r"\*\*Refills\*\*:\s*(.+?)(\n|$)", block)

            instr_match = re.search(
                r"\*\*(?:Special Instructions|Special Instructions or Warnings)\*\*:\s*(.+?)(\n|$)",
                block,
            )
            instructions = instr_match.group(1).strip() if instr_match else ""

            if cleaned_name:
                meds.append({
                    "name": cleaned_name,
                    "dosage_and_route": dosage,
                    "frequency_and_duration": freq,
                    "refills": refills,
                    "special_instructions": instructions,
                })
        return meds

    def _extract_list_items(section: str, name_key: str, detail_key: str = "details") -> List[Dict]:
        if not section:
            return []
        items = []
        for line in section.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^(?:\d+[\.\)]|\-|\*)\s*(\*\*(.+?)\*\*:)?\s*(.+)", line)
            if match:
                title = (match.group(2) or match.group(3)).strip()
                detail = match.group(3).strip()
                items.append({name_key: title, detail_key: {"text": detail}})
        return items

    # Patient info
    age_str = extract_field(r",\s*(\d+)\s*years? old", default="0")
    try:
        age = int(age_str)
    except ValueError:
        age = 0

    patient_info = {
        "name": extract_field(r"\*\*Patient Information\*\*:\s*([\w\s]+),"),
        "age": age,
        "gender": extract_field(r"Gender:\s*([A-Za-z]+)"),
        "date": extract_field(r"\*\*Date\*\*:\s*(.+?)(?=\n\*\*|$)", default=""),
    }

    diagnosis = extract_field(r"\*\*Diagnosis\*\*:\s*(.*?)(?=\n\*\*|$)")

    med_match = re.search(
        r"\*\*Medication\*\*:?(.*?)(\*\*Non-Pharmacological Recommendations\*\*|\*\*Medical Tests Recommended\*\*|\*\*Follow-Up\*\*|\*\*Prescriber\*\*|$)",
        text,
        re.DOTALL,
    )
    medications = extract_medications(med_match.group(1)) if med_match else []

    non_pharm_match = re.search(
        r"\*\*Non-Pharmacological Recommendations\*\*:?(.*?)(\*\*Medical Tests Recommended\*\*|\*\*Follow-Up\*\*|\*\*Prescriber\*\*|$)",
        text,
        re.DOTALL,
    )
    non_pharm_recs = (
        _extract_list_items(non_pharm_match.group(1), "title") if non_pharm_match else []
    )

    test_match = re.search(
        r"\*\*Medical Tests Recommended\*\*:?(.*?)(\*\*Follow-Up\*\*|\*\*Prescriber\*\*|$)",
        text,
        re.DOTALL,
    )
    medical_tests = (
        _extract_list_items(test_match.group(1), "test_name") if test_match else []
    )

    prescriber = extract_field(r"\*\*Prescriber\*\*:\s*(.+?)(?=\n|$)").rstrip("-").strip()

    return {
        "patient_info": patient_info,
        "diagnosis": diagnosis,
        "medication": medications,
        "non_pharmacological_recommendations": non_pharm_recs,
        "medical_tests": medical_tests,
        "prescriber": {"name": prescriber},
    }


# ---------- Public API ----------

def extract_prescription_data(text: str) -> Dict:
    """
    Extract structured prescription data from LLM output.

    Tries to parse as structured JSON first (from ``response_format``).
    Falls back to regex-based extraction from markdown text.
    """
    # Try structured JSON first
    result = parse_structured_json(text)
    if result is not None:
        logger.info("Parsed prescription via structured JSON output.")
        return result

    # Fallback to regex
    logger.info("Falling back to regex-based prescription extraction.")
    return _extract_prescription_regex(text)
