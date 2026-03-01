import os
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"  # Skip slow connectivity check on startup

# Monkey-patch: paddlex imports langchain.docstore which was removed in langchain>=1.0.
# Redirect it to langchain_core.documents so paddleocr can load without errors.
import importlib, types
_langchain_docstore = types.ModuleType("langchain.docstore")
_langchain_docstore_document = types.ModuleType("langchain.docstore.document")
try:
    from langchain_core.documents import Document
    _langchain_docstore_document.Document = Document
except ImportError:
    pass
import sys
sys.modules.setdefault("langchain.docstore", _langchain_docstore)
sys.modules.setdefault("langchain.docstore.document", _langchain_docstore_document)

from paddleocr import PaddleOCR  # Import the PaddleOCR class

# Initialize the OCR model with optional document-related features disabled
ocr = PaddleOCR(
    use_doc_orientation_classify=False,  # Disable document orientation classification
    use_doc_unwarping=False,  # Disable unwarping of curved documents
    use_textline_orientation=False  # Disable detection of text line orientation
)

# Function to perform OCR on the given image path
def perform_ocr(path_to_test):
    result = ocr.predict(
        input=path_to_test  # Run OCR prediction on the input image
    )

    for res in result:
        res.save_to_img("output")  # Save OCR-annotated image to the "output" folder
        res.save_to_json("output")  # Save OCR result in JSON format to the "output" folder
