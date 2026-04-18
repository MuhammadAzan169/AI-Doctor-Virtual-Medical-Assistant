import os
import json
import logging

logger = logging.getLogger(__name__)

# Lazy singleton — created on first call
_ocr_instance = None


def _get_ocr():
    """Lazily import PaddleOCR and create the singleton on first use."""
    global _ocr_instance
    if _ocr_instance is None:
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

        # Monkey-patch: paddlex imports langchain.docstore which was removed in langchain>=1.0.
        import types, sys
        _langchain_docstore = types.ModuleType("langchain.docstore")
        _langchain_docstore_document = types.ModuleType("langchain.docstore.document")
        try:
            from langchain_core.documents import Document
            _langchain_docstore_document.Document = Document
        except ImportError:
            pass
        sys.modules.setdefault("langchain.docstore", _langchain_docstore)
        sys.modules.setdefault("langchain.docstore.document", _langchain_docstore_document)

        from paddleocr import PaddleOCR
        logger.info("Initializing PaddleOCR...")
        _ocr_instance = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        logger.info("PaddleOCR ready.")
    return _ocr_instance


def perform_ocr(image_path: str, output_dir: str = "output") -> str:
    """
    Run OCR on *image_path* and write results to a session-specific
    output directory.  Returns the path to the generated JSON file,
    or None on failure.
    """
    os.makedirs(output_dir, exist_ok=True)
    ocr = _get_ocr()

    try:
        result = ocr.predict(input=image_path)
    except Exception:
        logger.exception("OCR prediction failed for %s", image_path)
        return None

    json_path = None
    input_stem = os.path.splitext(os.path.basename(image_path))[0]
    for res in result:
        res.save_to_json(output_dir)
        # PaddleOCR v3 names the file after the input image stem: {stem}.json
        candidate = os.path.join(output_dir, f"{input_stem}.json")
        if os.path.exists(candidate):
            json_path = candidate
            break
        # Fallback: pick any .json file written into the output directory
        json_files = [
            os.path.join(output_dir, f)
            for f in os.listdir(output_dir)
            if f.endswith(".json")
        ]
        if json_files:
            json_path = json_files[0]
            break

    return json_path
