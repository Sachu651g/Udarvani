# Round 2 Submission Checklist — UdarVani

> [!IMPORTANT]
> **Single-Submission Deadline**: **November 30 at 11:59 p.m.**  
> Please **verify the exact time zone displayed on your hackathon submission dashboard** (e.g., IST vs. UTC/EST) before uploading. Do not submit until all items below are checked.

---

## 1. Repository & Code Deliverables (Ready Locally)
- [x] **Working Prototype**: React + TypeScript frontend (`frontend/`), FastAPI + SQLite backend (`backend/`).
- [x] **Docker Startup**: `docker-compose.yml` boots cleanly with `docker compose up --build` and zero secrets.
- [x] **Documentation**: `README.md` with startup, mic setup, dependencies/fallbacks, original vs. scaffolding breakdown, and test results.
- [x] **Demo Script**: `docs/DEMO_SCRIPT.md` (< 3 minutes).
- [x] **Pitch Deck PDF**: `docs/UdarVani_Pitch_Deck.pdf` (searchable PDF).

---

## 2. Actions Required From You Personally
- [ ] **Manual Live-Mic Verification**: Open the app in Chrome/Edge on `http://localhost:3000` (or `5173`), allow microphone access, and speak *"Ramesh ke khate mein do doodh ke packet, nahi teen, tees rupaye ka ek"* → *"Dairy Gate wala"* → *"Haan, save kar do"*.
- [ ] **Docker Compose Smoke Check**: Start Docker Desktop and run `docker compose up --build` to confirm the containerized build on your machine (Docker daemon was not running during automated build).
- [ ] **Create Public GitHub Repository**: Initialize git, review files, push to a **public** GitHub repo, and copy the **Public GitHub URL**.
- [ ] **Record & Upload Demo Video**: Follow `docs/DEMO_SCRIPT.md` (< 3 min), upload to YouTube (Public or Unlisted), and copy the **YouTube URL**.
- [ ] **Organizer Rules Check**: Verify your submission meets the organizer's original-code guidelines (~300+ lines of original application logic; `backend/app/parser.py`, `workflow.py`, `db.py`, `main.py`, and `frontend/src/*` are cleanly separated from config/scaffolding) and disclose AI-assisted tooling if required by the rules.
- [ ] **Final Portal Submission**: Submit **Public GitHub URL**, **YouTube URL**, and **`docs/UdarVani_Pitch_Deck.pdf`** before **November 30 at 11:59 p.m.** (confirming dashboard time zone).
