import json
import logging

logger = logging.getLogger(__name__)


def extract_text_from_json(json_path: str) -> str:
    """
    Read an OCR JSON file (with ``rec_texts`` and ``rec_boxes`` keys),
    reconstruct the text in reading order (top-to-bottom, left-to-right),
    and return it as a single string.

    Returns an empty string if the file is missing required keys or
    contains no text entries.
    """
    with open(json_path) as f:
        data = json.load(f)

    # PaddleOCR v3 may wrap everything under a "res" key
    if "res" in data and isinstance(data["res"], dict):
        data = data["res"]

    texts = data.get("rec_texts")
    boxes = data.get("rec_boxes")

    if not texts or not boxes:
        # Fallback: try to just concatenate all text if available
        if texts and not boxes:
            return " ".join(t for t in texts if t)
        logger.warning("OCR JSON missing rec_texts/rec_boxes in %s", json_path)
        return ""

    if len(texts) != len(boxes):
        logger.warning("Mismatched texts/boxes count in %s", json_path)

    entries = []
    for i, box in enumerate(boxes):
        if i >= len(texts):
            break
        x_min, y_min, x_max, y_max = box
        center_y = (y_min + y_max) / 2
        entries.append({
            "text": texts[i],
            "y_min": y_min,
            "y_max": y_max,
            "x_min": x_min,
            "x_max": x_max,
            "center_y": center_y,
        })

    if not entries:
        return ""

    sorted_entries = sorted(entries, key=lambda e: e["center_y"])

    rows = []
    current_row = [sorted_entries[0]]

    for entry in sorted_entries[1:]:
        last_in_row = current_row[-1]

        y_overlap = min(entry["y_max"], last_in_row["y_max"]) - max(
            entry["y_min"], last_in_row["y_min"]
        )
        height = min(
            entry["y_max"] - entry["y_min"],
            last_in_row["y_max"] - last_in_row["y_min"],
        )

        if height > 0 and y_overlap > height * 0.6:
            current_row.append(entry)
        else:
            rows.append(sorted(current_row, key=lambda e: e["x_min"]))
            current_row = [entry]

    rows.append(sorted(current_row, key=lambda e: e["x_min"]))

    output_lines = []
    for row in rows:
        line_parts = []
        current_x = 0

        for i, entry in enumerate(row):
            if entry["x_min"] > current_x and i > 0:
                gap = entry["x_min"] - current_x
                line_parts.append(" " * max(1, int(gap / 10)))
            line_parts.append(entry["text"])
            current_x = entry["x_max"]

        output_lines.append("".join(line_parts))

    return "\n".join(output_lines)
