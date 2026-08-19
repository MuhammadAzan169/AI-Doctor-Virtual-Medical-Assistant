# AI Doctor — Virtual Medical Assistant: API Documentation

**Framework**: FastAPI (Python)  
**Deployed on**: Render  
**Base URL**: `https://<your-render-service>.onrender.com`  
**API Docs (Swagger UI)**: `https://<your-render-service>.onrender.com/docs`

---

## Table of Contents

1. [CORS & Request Requirements](#cors--request-requirements)
2. [System Routes](#system-routes)
3. [Consultation Routes](#consultation-routes)
4. [Media Routes](#media-routes)
5. [Session Flow](#session-flow)
6. [Error Reference](#error-reference)
7. [Frontend Checklist](#frontend-checklist)

---

## CORS & Request Requirements

| Setting | Value |
|--------|-------|
| Allowed Origins | `*` (or comma-separated list via `ALLOWED_ORIGINS` env var) |
| Allowed Methods | `GET`, `POST`, `OPTIONS` |
| Allowed Headers | `*` |
| Credentials | Not required |

> **Important**: Multipart form-data endpoints require `Content-Type: multipart/form-data`. Do **not** manually set this header — let the browser/fetch API set it automatically so the boundary is included.

---

## System Routes

### `GET /`

Health check and API info.

**Request**: No body, no params.

**Response** `200 OK`:
```json
{
  "name": "AI Doctor — Virtual Medical Assistant",
  "version": "2.0.0",
  "docs": "/docs",
  "health": "/health"
}
```

---

### `GET /health`

Checks which optional ML features are active on the server.

**Request**: No body, no params.

**Response** `200 OK`:
```json
{
  "status": "healthy",
  "features": {
    "fracture_detection": true,
    "ocr": true,
    "voice": false
  }
}
```

> Use this endpoint on app load to conditionally show/hide X-ray upload, report upload, and voice input UI elements.

---

## Consultation Routes

All consultation routes are prefixed with `/api`.

---

### `POST /api/start-consultation`

Starts a new consultation session. Optionally accepts an X-ray image and/or a medical report.

**Content-Type**: `multipart/form-data`

**Form Fields**:

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `name` | string | Yes | 1–100 characters | Patient name |
| `age` | integer | Yes | 0–120 | Patient age |
| `gender` | string | Yes | — | Patient gender (e.g., `"male"`, `"female"`) |
| `xray` | file | No | Max 10 MB | X-ray image for fracture detection (JPEG, PNG) |
| `report` | file | No | Max 10 MB | Medical report file (PNG, JPG, JSON, etc.) for OCR |

**Frontend Example (fetch)**:
```js
const formData = new FormData();
formData.append("name", "John Doe");
formData.append("age", 30);
formData.append("gender", "male");
// Optional:
formData.append("xray", xrayFileInput.files[0]);
formData.append("report", reportFileInput.files[0]);

const res = await fetch(`${BASE_URL}/api/start-consultation`, {
  method: "POST",
  body: formData
  // DO NOT set Content-Type header manually
});
const data = await res.json();
```

**Response** `200 OK`:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Welcome, John Doe. Please describe your symptoms.",
  "phase": "awaiting_symptom"
}
```

> **Save `session_id`** — it is required for all subsequent `/api/chat` and `/api/prescription/{session_id}` calls.

---

### `POST /api/chat`

Send a message or answer within an active consultation session.

**Content-Type**: `application/json`

**Request Body**:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "I have a headache and fever for 2 days."
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `session_id` | string | Yes | UUID from `/api/start-consultation` |
| `message` | string | Yes | Max 5000 characters |

**Frontend Example (fetch)**:
```js
const res = await fetch(`${BASE_URL}/api/chat`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    session_id: sessionId,
    message: userMessage
  })
});
const data = await res.json();
```

**Response** `200 OK` — during questioning phase:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "How severe is your headache on a scale of 1–10?",
  "phase": "questioning",
  "prescription_ready": false,
  "prescription": null
}
```

**Response** `200 OK` — when consultation is complete:
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Your consultation is complete. Your prescription is ready.",
  "phase": "complete",
  "prescription_ready": true,
  "prescription": {
    "patient_info": {
      "name": "John Doe",
      "age": 30,
      "gender": "male",
      "date": "2026-06-14"
    },
    "diagnosis": "Viral fever with tension headache",
    "medication": [
      {
        "name": "Paracetamol",
        "dosage_and_route": "500mg oral",
        "frequency_and_duration": "Every 6 hours for 5 days",
        "refills": "0",
        "special_instructions": "Take after food"
      }
    ],
    "non_pharmacological_recommendations": [
      {
        "title": "Rest",
        "details": { "text": "Get adequate rest and sleep." }
      }
    ],
    "medical_tests": [
      {
        "test_name": "CBC",
        "details": { "text": "Complete blood count to rule out infection." }
      }
    ],
    "prescriber": { "name": "AI Doctor" },
    "reasoning": "Patient presents with classic viral fever symptoms..."
  }
}
```

**Session Phases**:

| Phase | Description |
|-------|-------------|
| `awaiting_symptom` | Session started, waiting for first symptom message |
| `questioning` | AI is asking follow-up questions (up to 8 by default) |
| `generating` | AI is generating the prescription (transient, usually not seen) |
| `complete` | Consultation done, prescription available |

---

### `GET /api/prescription/{session_id}`

Download the generated prescription as a PDF file.

**URL Parameter**:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | Yes | UUID from session |

**Response**: Binary PDF file  
**Content-Type**: `application/pdf`  
**Filename**: `prescription.pdf`

**Frontend Example (download)**:
```js
const res = await fetch(`${BASE_URL}/api/prescription/${sessionId}`);
const blob = await res.blob();
const url = URL.createObjectURL(blob);

// Option A: Open in new tab
window.open(url);

// Option B: Trigger download
const a = document.createElement("a");
a.href = url;
a.download = "prescription.pdf";
a.click();
```

**Error** `404 Not Found` — session does not exist or has expired:
```json
{ "detail": "Session not found" }
```

---

## Media Routes

Both media routes are prefixed with `/api`.

---

### `POST /api/voice-input`

Transcribes an uploaded audio file to text (requires `ENABLE_VOICE=true` on server).

**Content-Type**: `multipart/form-data`

**Form Fields**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audio` | file | Yes | Audio file to transcribe (WAV, MP3, M4A, etc.) |

**Frontend Example (fetch)**:
```js
const formData = new FormData();
formData.append("audio", audioFile);

const res = await fetch(`${BASE_URL}/api/voice-input`, {
  method: "POST",
  body: formData
});
const data = await res.json();
// data.text => transcribed string
```

**Response** `200 OK`:
```json
{
  "text": "I have a headache and fever for two days."
}
```

**Error** `503 Service Unavailable` — voice feature disabled:
```json
{ "detail": "Voice transcription is not enabled on this server." }
```

---

### `POST /api/tts`

Converts text to an MP3 audio file (text-to-speech).

**Content-Type**: `multipart/form-data`

**Form Fields**:

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `text` | string | Yes | Max 5000 characters | Text to convert to speech |

**Frontend Example (fetch)**:
```js
const formData = new FormData();
formData.append("text", "Please describe your symptoms.");

const res = await fetch(`${BASE_URL}/api/tts`, {
  method: "POST",
  body: formData
});
const blob = await res.blob();
const audioUrl = URL.createObjectURL(blob);
const audio = new Audio(audioUrl);
audio.play();
```

**Response**: Binary MP3 file  
**Content-Type**: `audio/mpeg`  
**Filename**: `speech.mp3`

**Error** `400 Bad Request` — invalid or empty text:
```json
{ "detail": "Text cannot be empty." }
```

---

## Session Flow

```
1. POST /api/start-consultation
        ↓
   Save session_id
        ↓
2. POST /api/chat  (message = initial symptom)
        ↓
   phase: "questioning"
        ↓
3. POST /api/chat  (message = answer to AI question)
   ... repeat up to 8 rounds ...
        ↓
   phase: "complete", prescription_ready: true
        ↓
4. GET /api/prescription/{session_id}
   → Download PDF
```

**Session TTL**: 1 hour (3600 seconds). After expiry, the `session_id` becomes invalid and calls return `404`.

---

## Error Reference

| HTTP Status | Meaning | Common Cause |
|------------|---------|--------------|
| `400` | Bad Request | Empty message, unsupported file type, text too long |
| `404` | Not Found | Session expired or invalid `session_id` |
| `413` | Payload Too Large | Uploaded file exceeds 10 MB limit |
| `503` | Service Unavailable | Optional feature (voice/fracture/OCR) disabled on server, **or** every configured LLM model/key failed |
| `422` | Unprocessable Entity | FastAPI validation error — missing required field or wrong type |
| `500` | Internal Server Error | Server-side exception (check `/health` and server logs) |

---

## Frontend Checklist

Use this checklist to verify your frontend is calling the API correctly:

### Start Consultation
- [ ] Using `FormData` — NOT `JSON.stringify`
- [ ] **NOT** manually setting `Content-Type` header (let browser set it)
- [ ] `age` is sent as a number, not a string
- [ ] Storing `session_id` from response in state/localStorage
- [ ] Checking `/health` on load to show/hide xray & report upload fields

### Chat
- [ ] Using `Content-Type: application/json` header
- [ ] Sending body as `JSON.stringify({ session_id, message })`
- [ ] Checking `prescription_ready === true` to show "Download PDF" button
- [ ] Checking `phase` value to update UI state (e.g., show spinner during `generating`)

### Prescription PDF
- [ ] Using the correct `session_id` (same one from `/api/start-consultation`)
- [ ] Handling the binary blob with `res.blob()`, not `res.json()`
- [ ] Calling this only after `prescription_ready === true`

### Voice Input
- [ ] Checking `/health` → `features.voice === true` before showing mic button
- [ ] Uploading audio as `FormData` with key `"audio"`
- [ ] Using the returned `text` to populate the chat input field

### TTS
- [ ] Sending `text` as `FormData` (not JSON)
- [ ] Consuming response as `res.blob()` and playing with `new Audio(...)`

### General
- [ ] Base URL has no trailing slash
- [ ] Not sending `Authorization` headers (no auth required)
- [ ] Handling `404` — show "Session expired, please restart" message
- [ ] Handling `503` — gracefully disabling the affected feature in UI

---

## Complete Endpoint Summary

| Method | Endpoint | Content-Type | Auth | Description |
|--------|----------|-------------|------|-------------|
| GET | `/` | — | None | API info |
| GET | `/health` | — | None | Feature health check |
| POST | `/api/start-consultation` | `multipart/form-data` | None | Create session |
| POST | `/api/chat` | `application/json` | None | Send message |
| GET | `/api/prescription/{session_id}` | — | None | Download PDF |
| POST | `/api/voice-input` | `multipart/form-data` | None | Audio → Text |
| POST | `/api/tts` | `multipart/form-data` | None | Text → Audio |
