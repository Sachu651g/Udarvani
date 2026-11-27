# UdarVani — Voice-First Kirana Credit Ledger

**UdarVani** is a voice-first credit (*udhaar*) ledger built for small Indian kirana shops. A busy shopkeeper can record a credit sale by speaking naturally in **Hindi, English, or Hinglish**, resolve ambiguous customer names, correct mistakes mid-sentence or afterward, hear a spoken readback of the total, and save to a persistent SQLite ledger **only after explicit confirmation**.

---

## Key Features

- **Natural Hinglish / Hindi / English Parsing**: Understands phrases like:
  > *"Ramesh ke khate mein do doodh ke packet, nahi teen, tees rupaye ka ek."*
  Extracts customer (`Ramesh`), item (`Doodh ke packet`), corrected quantity (`2 → 3`), unit price (`₹30`), and total (`3 × ₹30 = ₹90`).
- **Duplicate Customer Clarification**: Seeded with two distinguishable *Ramesh* accounts (`Ramesh Kumar — Dairy Gate / डेयरी गेट` and `Ramesh Sharma — Station Road / स्टेशन रोड`). Prompts for clarification and accepts either a spoken choice (*"Dairy Gate wala"*) or a tap.
- **Spoken Corrections & Missing-Field Recovery**: Replaces previous values when corrected (`nahi`, `actually`, `नहीं`) and blocks confirmation if required fields (such as unit price) are missing.
- **Readback & Explicit Confirmation**: Reads back customer, quantity, and total via browser `speechSynthesis` before saving. Cancelled or unconfirmed drafts **never** write to the ledger. Duplicate confirmations are idempotent.
- **Browser Speech Recognition + Accessible Fallback**: Uses the Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`) with `hi-IN` and `en-IN` modes, detects unsupported browsers, denied mic permissions, and recognition errors, and provides a clearly labeled **Transcript Input** for testing and accessibility.
- **Zero Secrets / Zero Paid APIs**: Runs 100% locally with FastAPI, SQLite, and React/TypeScript.

---

## Quick Start (Docker Compose)

A fresh checkout boots with a single command and requires **no API keys or secrets**:

```bash
docker compose up --build
```

- **App UI**: [http://localhost:3000](http://localhost:3000)
- **Backend API**: [http://localhost:8000/api/health](http://localhost:8000/api/health)
- **Persistence**: Confirmed entries are stored in the `udarvani_data` Docker volume (`/app/data/udarvani.db`) and survive container restarts.

---

## Local Development (Without Docker)

### 1. Backend (FastAPI + SQLite)
```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend (React + TypeScript + Vite)
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api/*` to `http://127.0.0.1:8000`.

---

## Microphone Setup & Browser Compatibility

- **Recommended Browsers**: Google Chrome or Microsoft Edge (desktop or Android) on `localhost` or `https://`, which support the Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`).
- **Permissions**: When you tap **Tap & Speak Sale**, allow microphone access if prompted.
- **Failure & Fallback Handling**:
  - **Unsupported Browser** (e.g., Firefox or restricted WebViews): Displays an explicit notice and keeps the **Transcript Input** ready.
  - **Denied Mic Permission / No Speech / Network Error**: Displays a clear recovery banner without simulating fake recognition.
  - **Transcript Input**: Always available for accessibility, quiet environments, and automated testing.

---

## Dependencies & Fallback Plans

| Layer | Dependency | Purpose | Fallback if Unavailable / Fails |
| :--- | :--- | :--- | :--- |
| **Speech-to-Text** | Browser Web Speech API (`hi-IN` / `en-IN`) | Free, zero-key voice capture | Transcript Input field; future offline Whisper.cpp / Vosk small-Hindi sidecar |
| **Text-to-Speech** | Browser `window.speechSynthesis` | Spoken confirmation readback | Visual high-contrast readback banner on screen |
| **NLU / Parser** | Custom Python deterministic parser (`backend/app/parser.py`) | Hinglish numbers, corrections, intent | No external API dependency; fully offline and testable |
| **Backend** | FastAPI + Uvicorn + Pydantic | REST API & draft state machine | Standard Python ASGI stack |
| **Database** | SQLite (`udarvani.db`) | Zero-config persistent storage | File-based backup or drop-in migration to PostgreSQL if multi-terminal sync is needed |
| **Frontend** | React 19 + TypeScript + Vite | Mobile-first shop UI | Static bundle served by Nginx |

---

## Original Application Logic vs. Scaffolding

To keep original hackathon logic clearly separated from framework scaffolding and dependencies:

- **Original Application Logic**:
  - `backend/app/parser.py`: Hinglish/Hindi/English number & unit extraction, inline and follow-up correction detection, duplicate-customer matching, confirmation/cancellation intent detection.
  - `backend/app/workflow.py`: Draft state machine (`clarification_needed`, `awaiting_confirmation`, `saved`, `cancelled`), readback generation, idempotent commit logic.
  - `backend/app/db.py`: SQLite schema, idempotent customer seeding, draft & ledger persistence.
  - `backend/app/main.py`: API endpoints connecting the workflow to the frontend.
  - `backend/tests/test_ledger.py`: Automated test suite covering corrections, duplicate names, missing price, cancellation, duplicate confirmation, totals, and persistence.
  - `frontend/src/App.tsx`, `frontend/src/hooks/useSpeechRecognition.ts`, `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/styles.css`: Voice capture, error recovery, live status UI, and ledger views.
- **Tooling / Configuration**: `package.json`, `tsconfig.json`, `vite.config.ts`, `Dockerfile`s, `nginx.conf`, `docker-compose.yml`.

---

## Verification & Test Results

- **Backend Automated Tests (`pytest`)**: 5/5 tests passing in `backend/tests/test_ledger.py` covering:
  1. Quantity correction (`2 → 3`), duplicate *Ramesh* clarification, spoken confirmation, and `₹90` total.
  2. Missing unit price blocking confirmation until provided.
  3. Draft cancellation (voice and button) never writing to the ledger.
  4. Duplicate confirmation idempotency (no duplicate rows).
  5. Price correction (`₹20 → ₹30`) and SQLite persistence across app restarts.
- **Frontend Build**: `tsc -b && vite build` succeeds with 0 errors.
- **Browser UI Verification**: Verified end-to-end in headless Chromium against the running FastAPI + Vite servers (including page refresh persistence). Note: Live human microphone audio capture requires manual human testing in Chrome/Edge; automated browser tests verified the UI, API integration, and transcript fallback without simulating speech recognition.

---

## Proposed 50-Shop Pilot & Targets

- **Pilot Scope**: 50 neighborhood *kirana* shops using synthetic-free local rollouts on shop Android phones / counter browsers.
- **Target Metrics (Proposed Targets — Not Measured Outcomes)**:
  - **80%** voice adoption for daily credit & sale entries
  - **90%** correct entries with at most one spoken correction
  - **20%** reduction in average days overdue via promised-date tracking & polite reminders
- **Language Roadmap**: Active Hindi/Hinglish & English (`hi-IN` / `en-IN`); Kannada, Tamil, and Marathi are planned as future additions and are not claimed as working until real speech tests are completed.
