"""X-ray fracture detection (ResNet50, TensorFlow). Gated by ENABLE_FRACTURE.

TF/Keras and the ~376 MB of model weights load lazily on first prediction.
"""

import importlib.util

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("AIDoctor.Fracture")

_tf = None
_preprocess_input = None
_load_img = None
_img_to_array = None
_np = None
_models: dict = {}

MODEL_FILES = {
    "body_parts": "ResNet50_BodyParts.h5",
    "elbow_frac": "ResNet50_Elbow_frac_best.h5",
    "hand_frac": "ResNet50_Hand_frac_best.h5",
    "shoulder_frac": "ResNet50_Shoulder_frac_best.h5",
}
CATEGORIES_PARTS = ["elbow", "wrist", "shoulder"]
CATEGORIES_FRACTURE = ["fractured", "normal"]
PART_TO_MODEL_KEY = {"wrist": "hand_frac", "elbow": "elbow_frac", "shoulder": "shoulder_frac"}
PART_DISPLAY_NAME = {"wrist": "Hand/Wrist", "elbow": "Elbow", "shoulder": "Shoulder"}


# Set when importing TensorFlow or loading a model raises. Being installed is
# not the same as being usable — a broken native/protobuf combination only
# surfaces at import time — and retrying a failed TF import on every upload is
# both slow and pointless.
_unusable_reason: str | None = None


def is_available() -> bool:
    """True only when the feature is enabled, installed, and known to import."""
    if not settings.ENABLE_FRACTURE:
        return False
    if importlib.util.find_spec("tensorflow") is None:
        logger.warning("ENABLE_FRACTURE=true but TensorFlow is not installed — feature disabled.")
        return False
    return _unusable_reason is None


def _ensure_imports():
    global _tf, _preprocess_input, _load_img, _img_to_array, _np
    if _tf is None:
        import numpy as np
        import tensorflow as tf
        from tensorflow.keras.applications.resnet50 import preprocess_input
        from tensorflow.keras.utils import img_to_array, load_img
        _tf, _np = tf, np
        _preprocess_input, _load_img, _img_to_array = preprocess_input, load_img, img_to_array
        logger.info("TensorFlow and Keras loaded.")


def _load_model(key: str):
    _ensure_imports()
    if key not in _models:
        path = settings.models_dir / MODEL_FILES[key]
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")
        logger.info("Loading model: %s", path)
        _models[key] = _tf.keras.models.load_model(str(path))
    return _models[key]


def _degraded(summary: str) -> dict:
    """A result shaped like a real prediction, for when we cannot make one."""
    return {
        "body_part": "unknown", "fracture_status": "unavailable",
        "body_part_confidence": 0.0, "fracture_confidence": 0.0,
        "summary": summary,
    }


def predict_fracture(image_path: str) -> dict:
    """Predict whether a bone in an X-ray is fractured.

    Never raises: this is an optional enrichment of a consultation, so a broken
    model degrades to a note in the transcript rather than failing the request.
    """
    if not is_available():
        return _degraded("X-ray analysis is not enabled on this server.")

    try:
        _ensure_imports()
    except Exception as exc:
        global _unusable_reason
        _unusable_reason = f"{exc.__class__.__name__}: {exc}"
        logger.exception("TensorFlow could not be imported — disabling X-ray analysis")
        return _degraded("X-ray analysis is unavailable on this server (the imaging model failed to load).")

    try:
        size = 224
        temp_img = _load_img(image_path, target_size=(size, size))
        x = _img_to_array(temp_img)
        x = _np.expand_dims(x, axis=0)
        images = _preprocess_input(x.copy())

        model_parts = _load_model("body_parts")
        part_probs = model_parts.predict(images, verbose=0)[0]
        part_idx = int(_np.argmax(part_probs))

        if part_idx >= len(CATEGORIES_PARTS):
            return {
                "body_part": "unknown", "fracture_status": "unknown",
                "body_part_confidence": 0.0, "fracture_confidence": 0.0,
                "summary": "Could not identify the body part in the X-ray.",
            }

        body_part = CATEGORIES_PARTS[part_idx]
        body_part_confidence = float(part_probs[part_idx])

        part_model = _load_model(PART_TO_MODEL_KEY[body_part])
        frac_probs = part_model.predict(images, verbose=0)[0]
        frac_idx = int(_np.argmax(frac_probs))
        fracture_status = CATEGORIES_FRACTURE[frac_idx]
        fracture_confidence = float(frac_probs[frac_idx])
        display_name = PART_DISPLAY_NAME[body_part]

        if fracture_confidence < 0.6:
            summary = f"Inconclusive result for {display_name} (confidence: {fracture_confidence:.0%}). A radiologist review is recommended."
        elif fracture_status == "fractured":
            summary = f"Fracture detected on {display_name} (confidence: {fracture_confidence:.0%})."
        else:
            summary = f"No fracture detected on {display_name} (confidence: {fracture_confidence:.0%})."

        return {
            "body_part": body_part,
            "fracture_status": fracture_status,
            "body_part_confidence": round(body_part_confidence, 4),
            "fracture_confidence": round(fracture_confidence, 4),
            "summary": summary,
        }
    except Exception:
        logger.exception("X-ray prediction failed for %s", image_path)
        return _degraded("The X-ray could not be analysed (the imaging model failed on this file).")
