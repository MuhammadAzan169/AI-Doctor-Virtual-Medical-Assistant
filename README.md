# AI Doctor — Virtual Medical Assistant

An AI-powered virtual medical assistant. A patient describes their symptoms, the
assistant conducts a symptom-based consultation with adaptive clinical follow-up
questions, and it generates a professional prescription as a downloadable PDF.
Optional locally-hosted AI models add X-ray fracture detection, lab-report OCR,
and voice interaction.

> **Not medical advice.** This is a software project for demonstration and
> educational use. It does not replace a qualified clinician.

---

## Contents

- [Key features](#key-features)
- [Project layout](#project-layout)
- [Prerequisites](#prerequisites)
- [Local installation](#local-installation)
- [Environment variables](#environment-variables)
- [Running the complete app locally](#running-the-complete-app-locally)
- [Local model configuration](#local-model-configuration)
- [API-based configuration](#api-based-configuration)
- [Local vs production behaviour](#local-vs-production-behaviour)
- [Deploying the backend to Render](#deploying-the-backend-to-render-free-plan)
- [Deploying the frontend to Vercel](#deploying-the-frontend-to-vercel)
- [Render free-plan limitations](#render-free-plan-limitations)
- [API reference](#api-reference)
- [Troubleshooting](#troubleshooting)

---

## Key features

- **Conversational AI doctor** — an OpenAI-compatible LLM (OpenRouter by
  default) runs a symptom-based consultation, asking adaptive follow-up
  questions before reaching a conclusion.
- **Prescription generation** — structured JSON extraction rendered into a
  professional PDF with ReportLab.
- **Medical image analysis** — ResNet50 models detect fractures in X-rays of the
  elbow, hand/wrist, and shoulder. *(local only)*
- **Lab-report processing** — PaddleOCR extracts test results from uploaded
  report images, reconstructed in reading order. *(local only)*
- **Voice interaction** — Whisper speech-to-text *(local only)* plus gTTS
  text-to-speech *(everywhere)*.
- **Web interface** — a dependency-free static site with an animated UI and a
  real-time chat interface.

Features marked *local only* cannot run on the Render free plan; see
[Local vs production behaviour](#local-vs-production-behaviour).

---

## Project layout

The repository root holds exactly four things:

```
.
├── app.py        ← run the COMPLETE app locally (backend + frontend, all models)
├── README.md     ← this file
├── Backend/      ← FastAPI service — deployed to Render
└── Frontend/     ← static site — deployed to Vercel
```

Everything each half needs to deploy lives inside its own folder:

```
Backend/
├── app/
│   ├── main.py                 FastAPI app factory, CORS, error handling
│   ├── core/config.py          all settings, read from the environment
│   ├── api/routes/             system · consultation · media endpoints
│   ├── services/               llm · consultation · pdf · fracture · ocr · stt · tts
│   └── assets/logo.png         used on the generated prescription
├── requirements.txt            LEAN deps — what Render installs
├── requirements-local.txt      FULL deps — lean set + all local AI/ML models
├── render.yaml                 Render service definition
├── Dockerfile                  optional container deploy
├── fracture_models/            ResNet50 .h5 weights (~376 MB, local use)
├── samples/xray/               sample X-rays for testing fracture detection
├── .env.example                environment template — copy to .env
└── API_DOCUMENTATION.md

Frontend/
├── index.html, chatbot.html    landing page + chat interface
├── assets/css/style.css, assets/logo.png
├── js/script.js                app logic
├── js/config.js                GENERATED — never edit or commit
├── build.mjs                   writes js/config.js from API_BASE_URL
├── vercel.json                 Vercel build config + security headers
└── .env.example
```

The frontend learns the backend URL from `window.APP_CONFIG.API_BASE_URL` in
`js/config.js`, which is **generated at build time** — by `build.mjs` on Vercel,
and by `app.py` for local runs. It is gitignored and must never be hand-edited.

On startup the frontend calls `GET /health` and hides whatever the backend
reports as unavailable (for example, the microphone button when voice is off),
so the same build works against a full local backend and a lean Render one.

---

## Prerequisites

| | Required for | Notes |
|---|---|---|
| **Python 3.10 – 3.12** | everything | 3.12 is what Render runs. TensorFlow has no 3.13 wheels yet. |
| **pip** | everything | |
| **An OpenRouter API key** | the consultation LLM | Free at <https://openrouter.ai>. Any OpenAI-compatible endpoint works. |
| **Node.js 18+** | Vercel builds, `npm run dev` | *Not* needed for `python app.py` — it writes `js/config.js` itself. |
| **ffmpeg on PATH** | Whisper voice input (local) | <https://ffmpeg.org/download.html> |

Disk: roughly 4–6 GB if you install every local model (TensorFlow, PaddlePaddle,
PyTorch), plus the ~376 MB of X-ray weights already in the repo.

---

## Local installation

```bash
git clone <your-repo-url>
cd AI-Doctor-Virtual-Medical-Assistant

python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

# FULL local stack — includes every model Render's free plan cannot run
pip install -r Backend/requirements-local.txt
```

If you only want the core consultation flow (fast install, no multi-GB
downloads), install the lean set instead. Every local AI/ML feature then reports
itself as unavailable and the app still runs:

```bash
pip install -r Backend/requirements.txt
```

Then create your environment file:

```bash
cd Backend
cp .env.example .env          # Windows: copy .env.example .env
cd ..
```

Open `Backend/.env` and set `LLM_API_KEY`. Nothing else is required to start.

---

## Environment variables

Secrets live in `Backend/.env` locally and in the platform dashboard in
production. **Never commit a real key** — `.env` is gitignored at every level,
and only the `.env.example` templates are tracked.

`app.py` reads `Backend/.env`. Real environment variables always take priority
over the file.

### Backend (`Backend/.env` locally, Render dashboard in production)

| Variable | Default | Purpose |
|---|---|---|
| `LLM_API_KEY` | *(empty)* | **Required.** OpenRouter (or other OpenAI-compatible) key. |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | LLM endpoint. `OPENROUTER_BASE_URL` is accepted as an alias. |
| `LLM_MODEL` | `openai/gpt-oss-20b:free` | Model id. Always kept as the **last-resort fallback**. |
| `LLM_PROVIDER` | `openrouter` | Label used in logs. |
| `LLM_MAX_TOKENS` | `3000` | Response cap. |
| `LLM_TEMPERATURE` | `0.3` | Sampling temperature. |
| `OPENROUTER_MODEL_1..5` | *(empty)* | Optional ordered model fallback chain. |
| `OPENROUTER_API_KEY1..N` | *(empty)* | Optional extra keys, rotated on rate-limit/auth errors. |
| `ENVIRONMENT` | `development` | `development` \| `production`. |
| `PORT` | `8000` | Render sets this automatically — do not override it there. |
| `LOG_LEVEL` | `INFO` | |
| `ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins, no trailing slash. Set to your Vercel URL in production. |
| `MAX_QUESTIONS` | `8` | Follow-up questions before the prescription is generated. |
| `MAX_MESSAGE_LENGTH` | `5000` | |
| `MAX_UPLOAD_SIZE_MB` | `10` | |
| `SESSION_TTL_SECONDS` | `3600` | Idle session expiry. |
| `ENABLE_FRACTURE` | `false` | X-ray fracture detection (TensorFlow). |
| `ENABLE_OCR` | `false` | Lab-report OCR (PaddleOCR). |
| `ENABLE_VOICE` | `false` | Speech-to-text (Whisper). |
| `WHISPER_MODEL_SIZE` | `medium` | `tiny` \| `base` \| `small` \| `medium` \| `large`. |
| `MODELS_DIR` | `Backend/fracture_models` | Where the `.h5` weights live. |
| `RUNTIME_DIR` | `Backend/var` | Writable dir for uploads/OCR output/PDFs. Use `/tmp/...` on Render. |

You do **not** need to set the `ENABLE_*` flags locally: `app.py` turns each one
on automatically when its dependency is importable.

### Frontend (`Frontend/.env` locally, Vercel dashboard in production)

| Variable | Purpose |
|---|---|
| `API_BASE_URL` | Base URL of the deployed backend, no trailing slash. Injected into `js/config.js` at build time. |

The frontend holds **no secrets**. Anything shipped to the browser is public, so
the LLM key stays server-side and every model call goes through the backend.

---

## Running the complete app locally

```bash
python app.py
```

That single command:

1. loads `Backend/.env`;
2. auto-detects which local models are installed and enables them;
3. writes `Frontend/js/config.js` pointing at the local API;
4. serves the frontend on <http://127.0.0.1:3000>;
5. serves the backend on <http://127.0.0.1:8000> (docs at `/docs`);
6. opens a browser.

Ctrl+C stops both. Local runs never talk to the deployed Render backend, so you
get the full feature set — including everything the free plan cannot host.

| Flag | Effect |
|---|---|
| `--backend-port N` | backend port (default `8000`) |
| `--frontend-port N` | frontend port (default `3000`) |
| `--no-browser` | do not open a browser |
| `--api-only` | backend only |
| `--reload` | auto-reload the backend on code changes |

Startup prints which local models are active:

```
  Local models  :
    fracture (TensorFlow) : on
    OCR (PaddleOCR)       : off (dependency not installed)
    voice (Whisper)       : on
```

### Running the pieces separately

```bash
# backend only
cd Backend && uvicorn app.main:app --reload

# frontend only (needs Node)
cd Frontend && npm run dev        # builds js/config.js, serves on :3000
```

---

## Local model configuration

Three features run on locally hosted models — the ones that **cannot** run on
the Render free plan. Each loads **lazily** on first use, so startup stays fast,
and each is gated by a flag *and* by whether its dependency is importable:
enabling a flag without the package installed degrades to a clean "not enabled"
response instead of crashing.

| Feature | Model | Package | Flag |
|---|---|---|---|
| X-ray fracture detection | ResNet50 `.h5` in `Backend/fracture_models/` | `tensorflow` | `ENABLE_FRACTURE` |
| Lab-report OCR | PaddleOCR (weights auto-downloaded on first run) | `paddleocr`, `paddlepaddle` | `ENABLE_OCR` |
| Voice input | OpenAI Whisper, running on your machine | `openai-whisper`, `torch` | `ENABLE_VOICE` |

All three come with `pip install -r Backend/requirements-local.txt`. To force a
feature off locally despite having the package, set it explicitly, e.g.
`ENABLE_VOICE=false`.

### How the model weights are stored

The four ResNet50 `.h5` files in `Backend/fracture_models/` are committed to git
as **normal files** (93.6 MB each, 375 MB total). Each is under GitHub's 100 MB
per-file hard limit, so a plain `git push` works — GitHub only prints a
size warning above 50 MB.

They are deliberately **not** tracked with Git LFS: GitHub's free tier allows
just 1 GB of LFS storage and 1 GB of bandwidth per month, which 375 MB of
weights would exhaust after about two clones. Keeping them as ordinary files
means `git clone` gives you a working local setup with no extra tooling.

The trade-off is that Render also clones them on every deploy even though it
never loads them (`ENABLE_FRACTURE=false`), which makes free-plan builds slower.
That is accepted so local development works out of the box. If you later want
faster deploys, add `fracture_models/` to `Backend/.gitignore` and distribute
the weights separately — the backend degrades cleanly when they are absent.

Test fracture detection with the sample X-rays in `Backend/samples/xray/`
(`elbow.jpg`, `shoulder.jpg`, `wrist.jpg`) — upload one on the consultation
form.

Whisper needs **ffmpeg** on your PATH. Use a smaller model
(`WHISPER_MODEL_SIZE=base`) on a machine without a GPU; `medium` is slow on CPU.
Fracture detection expects all four `.h5` files present in `MODELS_DIR`.

---

## API-based configuration

Two capabilities always go through an external API and therefore behave
identically locally and on Render:

- **Consultation LLM** — any OpenAI-compatible endpoint via the `openai` client,
  configured with `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY`.
- **Text-to-speech** — gTTS (Google Translate TTS). No key, needs outbound internet.

### LLM resilience

`Backend/app/services/llm.py` combines multi-key rotation with multi-model
fallback:

1. try the current key against the current model;
2. auth / rate-limit / provider-error → rotate to the next `OPENROUTER_API_KEY*`;
3. keys exhausted, or the model is rejected (400/404, e.g. a mistyped id) →
   move to the next model in the chain and reset to the first key;
4. everything exhausted → `LLMUnavailableError`, returned to the frontend as a
   clean **503** with a readable message rather than a 500 stack trace.

The chain is `OPENROUTER_MODEL_1..5` followed by `LLM_MODEL`, which is always
appended last so a typo in the chain cannot take the service down. Numbered keys
are read from the process environment (how Render supplies them) **and** from
`Backend/.env` (local convenience), so the same code path works in both places.

Watch the logs for `Model '…' rejected (BadRequestError)` — that means the id
does not exist on your provider; check the exact slug at
<https://openrouter.ai/models>.

---

## Local vs production behaviour

| | Local (`python app.py`) | Render free plan |
|---|---|---|
| Consultation LLM | API (OpenRouter) | API (OpenRouter) |
| Prescription PDF | ✅ ReportLab | ✅ ReportLab |
| Text-to-speech | ✅ gTTS (API) | ✅ gTTS (API) |
| X-ray fracture detection | ✅ local TensorFlow | ❌ off — too large for 512 MB |
| Lab-report OCR | ✅ local PaddleOCR | ❌ off — too large for 512 MB |
| Voice input (STT) | ✅ local Whisper | ❌ off — too large for 512 MB |
| Sessions | in-memory | in-memory (lost on sleep/restart) |
| Uploaded files | `Backend/var/` | `/tmp` — ephemeral |

Uploads are still accepted on Render; the response simply says the analysis is
not enabled on that server. The frontend hides the microphone button when
`/health` reports `voice: false`, so nothing appears broken to the user.

**In short:** the deployed site gives you the consultation, the prescription PDF
and text-to-speech. For fracture detection, lab-report OCR and voice input, run
`python app.py` locally.

---

## Deploying the backend to Render (free plan)

Because this is a monorepo, the service must be pointed at the `Backend/` folder.

**Manual setup (recommended)**

1. Push this repo to GitHub.
2. Render dashboard → **New +** → **Web Service** → select the repo.
3. Configure:

   | Setting | Value |
   |---|---|
   | Environment | Python 3 |
   | **Root Directory** | `Backend` |
   | Build command | `pip install --no-cache-dir -r requirements.txt` |
   | Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
   | Health check path | `/health` |
   | Instance type | Free |

4. Add the environment variables below.
5. Deploy, then check `https://<service>.onrender.com/health`.

**Blueprint alternative.** Render only auto-detects `render.yaml` at the *repo
root*. `Backend/render.yaml` holds the full service definition — to deploy via
Blueprint, copy it to the repo root and add `rootDir: Backend` under the
service. Otherwise use it as a reference for the dashboard fields.

### Required Render environment variables

| Variable | Value |
|---|---|
| `LLM_API_KEY` | **your OpenRouter key — set it in the dashboard, never in the repo** |
| `ALLOWED_ORIGINS` | your Vercel URL, e.g. `https://ai-doctor.vercel.app` (comma-separate to add more; no trailing slash) |

Recommended alongside them (these are the values `Backend/render.yaml` sets):
`PYTHON_VERSION=3.12`, `ENVIRONMENT=production`, `LOG_LEVEL=INFO`,
`ENABLE_FRACTURE=false`, `ENABLE_OCR=false`, `ENABLE_VOICE=false`,
`LLM_PROVIDER=openrouter`, `LLM_BASE_URL=https://openrouter.ai/api/v1`,
`LLM_MODEL=openai/gpt-oss-20b:free`, `LLM_MAX_TOKENS=3000`,
`LLM_TEMPERATURE=0.3`, `MAX_QUESTIONS=8`, `MAX_UPLOAD_SIZE_MB=10`,
`SESSION_TTL_SECONDS=3600`, `RUNTIME_DIR=/tmp/ai-doctor`.

Do **not** set `PORT` on Render — the platform injects it, and the start command
already binds to it.

`Backend/Dockerfile` is available if you would rather deploy with Docker.

---

## Deploying the frontend to Vercel

1. Vercel dashboard → **Add New** → **Project** → import the repo.
2. Set **Root Directory** to `Frontend`.
3. Framework preset: **Other**. `Frontend/vercel.json` supplies the build
   command (`node build.mjs`) and output directory.
4. Add the environment variable below, then deploy.

### Required Vercel environment variables

| Variable | Value |
|---|---|
| `API_BASE_URL` | your Render URL, e.g. `https://ai-doctor-api.onrender.com` (no trailing slash) |

Set it for **Production**, **Preview**, and **Development** so preview
deployments work too. `build.mjs` bakes it into `js/config.js`; because it is
read at build time, **changing it requires a redeploy**.

After deploying, go back to Render and put the Vercel URL into `ALLOWED_ORIGINS`,
otherwise the browser blocks every request with a CORS error.

---

## Render free-plan limitations

- **512 MB RAM / 0.1 CPU.** TensorFlow, PaddlePaddle, and PyTorch cannot fit,
  which is why fracture detection, OCR, and voice are disabled there. They stay
  fully available locally through `app.py`.
- **Cold starts.** The service sleeps after ~15 minutes idle; the next request
  takes **30–60 s** to wake it. The frontend health check allows 10 s and fails
  silently, so the first real request absorbs the wake-up delay.
- **No persistent disk.** `RUNTIME_DIR` points at `/tmp`; generated PDFs vanish
  on restart. Download the prescription in the same session.
- **In-memory sessions.** A restart drops all sessions; users must start over.
  Multi-instance scaling would need a shared store such as Redis.
- **Monthly build/run hours** are capped on the free plan.
- **No GPU.**

To enable the heavy features in production, move to an instance with 2 GB+ RAM,
change the build command to `pip install -r requirements-local.txt`, and flip the
corresponding `ENABLE_*` flags to `true`.

---

## API reference

Interactive docs: `/docs` (Swagger) and `/redoc`. Full details in
`Backend/API_DOCUMENTATION.md`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Service metadata |
| `GET` | `/health` | Status + which features are enabled |
| `POST` | `/api/start-consultation` | multipart: `name`, `age`, `gender`, optional `xray`, `report` → `session_id` |
| `POST` | `/api/chat` | JSON: `session_id`, `message` → next question, or the finished prescription |
| `GET` | `/api/prescription/{session_id}` | Download the prescription PDF |
| `POST` | `/api/voice-input` | multipart `audio` → transcript (503 when voice is off) |
| `POST` | `/api/tts` | form `text` → MP3 |

Flow: `start-consultation` → repeat `chat` until `phase` is `complete` and
`prescription_ready` is `true` → `GET /api/prescription/{session_id}`.

---

## Troubleshooting

**CORS error in the browser console.**
`ALLOWED_ORIGINS` on Render must contain the exact frontend origin — scheme
included, no trailing slash, no path. Restart the Render service after changing
it. Locally, `app.py` configures this for you.

**Frontend calls the wrong host / `localhost:8000` in production.**
`js/config.js` is generated. Set `API_BASE_URL` in Vercel and **redeploy** — the
value is baked in at build time, not read at runtime. Never edit `js/config.js`
by hand; both `build.mjs` and `app.py` overwrite it.

**The first request after a while takes a minute.**
Render free-plan cold start. Expected. Keep the tab open, or upgrade the plan.

**503 "The medical AI service is temporarily unavailable."**
Every configured model/key combination failed. Check the Render logs: a missing
`LLM_API_KEY`, an exhausted free-tier quota, or a model id your provider does
not recognise (`Model '…' rejected (BadRequestError)`). Verify slugs at
<https://openrouter.ai/models>.

**`ModuleNotFoundError: No module named 'app'` when running uvicorn manually.**
Run it from inside `Backend/`, not the repo root — the repo root contains
`app.py`, which would shadow the `Backend/app` package. `python app.py` handles
this automatically.

**Microphone button missing.**
`/health` reported `voice: false` — expected on Render, and expected locally
until `openai-whisper` is installed. Install it and restart `app.py`.

**Whisper fails with a file/format error.** Install **ffmpeg** and make sure it
is on your PATH.

**TensorFlow will not install.** You are probably on Python 3.13, which has no
TensorFlow wheels yet. Use Python 3.12. The rest of the app runs fine without it.

**PaddleOCR fails on first use.** It downloads its weights on first run, so it
needs internet then. Some `paddlex` builds import `langchain.docstore`, removed
in `langchain>=1.0`; `Backend/app/services/ocr.py` already shims this.

**Port already in use.** `python app.py --backend-port 8001 --frontend-port 3001`.

**Render build fails or the service is OOM-killed.** Confirm the Root Directory
is `Backend` so the lean `Backend/requirements.txt` is what gets installed (not
`requirements-local.txt`), and that the `ENABLE_*` flags are all `false`.

**Uploads return 413.** Files are capped at `MAX_UPLOAD_SIZE_MB` (10 MB).

**`git push` is slow, or GitHub warns about large files.** Expected: the four
X-ray model weights are 93.6 MB each. They are under the 100 MB hard limit, so
the push succeeds. Do **not** add a `*.h5` Git LFS rule — see
[How the model weights are stored](#how-the-model-weights-are-stored).

**Fracture detection says it is not enabled, locally.** Either `tensorflow` is
not installed (`pip install -r Backend/requirements-local.txt`) or the four
`.h5` files are missing from `Backend/fracture_models/`. `app.py` prints the
status of all three local models at startup.
