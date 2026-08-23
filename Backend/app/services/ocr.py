"""Lab-report OCR (PaddleOCR) + reading-order text reconstruction.

Gated by ENABLE_OCR. PaddleOCR loads lazily on first use.
"""

import importlib.util
import json
import os

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("AIDoctor.OCR")

_ocr_instance = None


def is_available() -> bool:
    """True only when the feature is enabled *and* PaddleOCR is installed."""
    if not settings.ENABLE_OCR:
        return False
    if importlib.util.find_spec("paddleocr") is None:
        logger.warning("ENABLE_OCR=true but paddleocr is not installed — feature disabled.")
        return False
    return True


def _get_ocr():
    """Lazily import PaddleOCR and create the singleton on first use."""
    global _ocr_instance
    if _ocr_instance is None:
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

        # Monkey-patch: paddlex imports langchain.docstore and langchain.text_splitter,
        # both removed in langchain>=1.0 and re-homed in langchain_core /
        # langchain_text_splitters. Alias them back so the paddlex import chain works.
        import sys
        import types

        _langchain_docstore = types.ModuleType("langchain.docstore")
        _langchain_docstore_document = types.ModuleType("langchain.docstore.document")
        try:
            from langchain_core.documents import Document

            _langchain_docstore_document.Document = Document
        except ImportError:
            pass
        sys.modules.setdefault("langchain.docstore", _langchain_docstore)
        sys.modules.setdefault("langchain.docstore.document", _langchain_docstore_document)

        _langchain_text_splitter = types.ModuleType("langchain.text_splitter")
        try:
            import langchain_text_splitters as _lts

            for _name in dir(_lts):
                if not _name.startswith("_"):
                    setattr(_langchain_text_splitter, _name, getattr(_lts, _name))
        except ImportError:
            logger.warning("langchain_text_splitters missing — paddlex import may fail.")
        sys.modules.setdefault("langchain.text_splitter", _langchain_text_splitter)

        from paddleocr import PaddleOCR

        logger.info("Initializing PaddleOCR...")
        _ocr_instance = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            # Mobile models: ~50x faster than the server pair on CPU, which is the
            # difference between a usable request and a multi-minute stall.
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="PP-OCRv5_mobile_rec",
            # Paddle's oneDNN kernel raises NotImplementedError on Windows
            # (ConvertPirAttribute2RuntimeAttribute), so keep it off.
            enable_mkldnn=False,
        )
        logger.info("PaddleOCR ready.")
    return _ocr_instance


# Longest edge fed to the detector. Bigger inputs cost time without helping
# accuracy on document scans, which are already well above the text-height floor.
_MAX_EDGE_PX = 1600


def _downscale_if_huge(image_path: str, output_dir: str) -> str:
    """Return a path to an image whose longest edge is <= _MAX_EDGE_PX."""
    try:
        from PIL import Image
    except ImportError:
        return image_path
    try:
        with Image.open(image_path) as im:
            if max(im.size) <= _MAX_EDGE_PX:
                return image_path
            scale = _MAX_EDGE_PX / max(im.size)
            resized = im.convert("RGB").resize(
                (max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                Image.LANCZOS,
            )
            stem = os.path.splitext(os.path.basename(image_path))[0]
            small = os.path.join(output_dir, f"{stem}_ocr_input.png")
            resized.save(small)
            logger.info("Downscaled %s -> %s for OCR", im.size, resized.size)
            return small
    except Exception:
        logger.exception("Downscale failed for %s — using original", image_path)
        return image_path


def perform_ocr(image_path: str, output_dir: str = "output") -> str | None:
    """Run OCR and write a JSON result; return the JSON path or None on failure."""
    os.makedirs(output_dir, exist_ok=True)
    try:
        ocr = _get_ocr()
    except Exception:
        # Installed is not the same as importable — a broken native/dependency
        # combination only shows up here, and must not fail the consultation.
        logger.exception("PaddleOCR could not be initialised — skipping OCR")
        return None
    ocr_input = _downscale_if_huge(image_path, output_dir)
    try:
        result = ocr.predict(input=ocr_input)
    except Exception:
        logger.exception("OCR prediction failed for %s", image_path)
        return None

    # PaddleOCR names the JSON after the file it actually consumed.
    input_stem = os.path.splitext(os.path.basename(ocr_input))[0]
    for res in result:
        res.save_to_json(output_dir)
        candidate = os.path.join(output_dir, f"{input_stem}.json")
        if os.path.exists(candidate):
            return candidate
        json_files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith(".json")]
        if json_files:
            return json_files[0]
    return None


def extract_text_from_json(json_path: str) -> str:
    """Reconstruct text from a PaddleOCR JSON in reading order (top-to-bottom, left-to-right)."""
    with open(json_path) as f:
        data = json.load(f)

    if "res" in data and isinstance(data["res"], dict):
        data = data["res"]

    texts = data.get("rec_texts")
    boxes = data.get("rec_boxes")
    if not texts or not boxes:
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
        entries.append({
            "text": texts[i], "y_min": y_min, "y_max": y_max,
            "x_min": x_min, "x_max": x_max, "center_y": (y_min + y_max) / 2,
        })
    if not entries:
        return ""

    sorted_entries = sorted(entries, key=lambda e: e["center_y"])
    rows = []
    current_row = [sorted_entries[0]]
    for entry in sorted_entries[1:]:
        last = current_row[-1]
        y_overlap = min(entry["y_max"], last["y_max"]) - max(entry["y_min"], last["y_min"])
        height = min(entry["y_max"] - entry["y_min"], last["y_max"] - last["y_min"])
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
