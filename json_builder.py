import re  # Regular expressions for pattern matching
import json  # For JSON handling (not used in this snippet)
from typing import List, Dict  # For type hints

# Main function to extract structured prescription data from unstructured text
def extract_prescription_data(text: str) -> Dict:

    # Helper function to extract a single field using regex
    def extract_field(pattern, source=None, default=""):
        src = source if source else text  # Use provided source or fall back to full text
        match = re.search(pattern, src, re.IGNORECASE | re.DOTALL)  # Search with regex pattern
        return match.group(1).strip() if match else default  # Return match or default value

    # Helper function to extract a list of medications from the medication section
    def extract_medications(section: str) -> List[Dict]:
        if not section or "Not applicable" in section or "No medication prescribed" in section:
            return []  # Return empty list if no medications are present

        meds = []  # List to store medication dictionaries

        # Split into individual medication blocks using common list indicators
        med_blocks = re.split(r"(?:\n|^)\s*(?:\d+[\.\)]|\-|\*)\s*(?=\*\*Name\*\*:)", section.strip())

        for block in med_blocks:
            block = block.strip()
            if not block:
                continue  # Skip empty blocks

            if not block.startswith("**Name**:"):
                block = "**Name**: " + block  # Ensure the block starts with Name field

            raw_name = extract_field(r"\*\*Name\*\*:\s*(.+?)(\n|$)", block)  # Extract name
            cleaned_name = re.sub(r"^\d+[\.\)]\s*", "", raw_name).strip()  # Remove bullet number if present

            dosage = extract_field(r"\*\*Dosage and Route\*\*:\s*(.+?)(\n|$)", block)  # Extract dosage
            freq = extract_field(r"\*\*Frequency and Duration\*\*:\s*(.+?)(\n|$)", block)  # Extract frequency
            refills = extract_field(r"\*\*Refills\*\*:\s*(.+?)(\n|$)", block)  # Extract refill info

            # Extract special instructions (supports slightly different field names)
            instr_match = re.search(r"\*\*(?:Special Instructions|Special Instructions or Warnings)\*\*:\s*(.+?)(\n|$)", block)
            instructions = instr_match.group(1).strip() if instr_match else ""

            # Add structured medication dictionary to list
            meds.append({
                "name": cleaned_name,
                "brand_names": [],  # Placeholder if brand names are to be added later
                "dosage_and_route": dosage,
                "frequency_and_duration": freq,
                "refills": refills,
                "special_instructions": instructions
            })

        return meds  # Return list of medications

    # Helper function to extract non-pharmacological recommendations
    def extract_non_pharm_recommendations(section: str) -> List[Dict]:
        if not section:
            return []  # Return empty list if section is missing
        recommendations = []
        lines = section.strip().split("\n")  # Split section into lines
        for line in lines:
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^(?:\d+[\.\)]|\-|\*)\s*(\*\*(.+?)\*\*:)?\s*(.+)", line)  # Extract title and details
            if match:
                title = match.group(2).strip() if match.group(2) else match.group(3).strip()
                detail = match.group(3).strip()
                recommendations.append({
                    "title": title,
                    "details": {"text": detail}
                })
        return recommendations  # Return list of recommendations

    # Helper function to extract medical test recommendations
    def extract_medical_tests(section: str) -> List[Dict]:
        if not section:
            return []  # Return empty list if section is missing
        tests = []
        lines = section.strip().split("\n")  # Split section into lines
        for line in lines:
            line = line.strip()
            if not line:
                continue
            match = re.match(r"^(?:\d+[\.\)]|\-|\*)\s*(\*\*(.+?)\*\*:)?\s*(.+)", line)  # Extract test title and detail
            if match:
                title = match.group(2).strip() if match.group(2) else match.group(3).strip()
                detail = match.group(3).strip()
                tests.append({
                    "test_name": title,
                    "details": {"text": detail}
                })
        return tests  # Return list of tests

    # Extract basic patient information using regex
    patient_info = {
        "name": extract_field(r"\*\*Patient Information\*\*:\s*([\w\s]+),"),  # Extract patient name
        "age": int(extract_field(r",\s*(\d+)\s*years? old", default="0")),  # Extract patient age
        "gender": extract_field(r"Gender:\s*([A-Za-z]+)"),  # Extract gender
        "date": extract_field(r"\*\*Date\*\*:\s*(.+?)(?=\n\*\*|$)", default="")  # Extract date
    }

    diagnosis = extract_field(r"\*\*Diagnosis\*\*:\s*(.*?)(?=\n\*\*|$)")  # Extract diagnosis section

    # Extract medication section between Medication and next header
    med_match = re.search(
        r"\*\*Medication\*\*:?(.*?)(\*\*Non-Pharmacological Recommendations\*\*|\*\*Medical Tests Recommended\*\*|\*\*Follow-Up\*\*|\*\*Prescriber\*\*|$)",
        text,
        re.DOTALL
    )
    medications = extract_medications(med_match.group(1)) if med_match else []  # Extract medication details

    # Extract non-pharmacological section
    non_pharm_match = re.search(
        r"\*\*Non-Pharmacological Recommendations\*\*:?(.*?)(\*\*Medical Tests Recommended\*\*|\*\*Follow-Up\*\*|\*\*Prescriber\*\*|$)",
        text,
        re.DOTALL
    )
    non_pharm_recs = extract_non_pharm_recommendations(non_pharm_match.group(1)) if non_pharm_match else []

    # Extract medical tests section
    test_match = re.search(
        r"\*\*Medical Tests Recommended\*\*:?(.*?)(\*\*Follow-Up\*\*|\*\*Prescriber\*\*|$)",
        text,
        re.DOTALL
    )
    medical_tests = extract_medical_tests(test_match.group(1)) if test_match else []

    # Extract prescriber name
    prescriber = extract_field(r"\*\*Prescriber\*\*:\s*(.+?)(?=\n|$)").rstrip("-").strip()

    # Return structured data as a dictionary
    return {
        "patient_info": patient_info,
        "diagnosis": diagnosis,
        "medication": medications,
        "non_pharmacological_recommendations": non_pharm_recs,
        "medical_tests": medical_tests,
        "prescriber": {
            "name": prescriber
        }
    }
