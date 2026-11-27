# UdarVani — Pitch Deck (Round 2: Livelihoods & Small Business)

---

## Slide 1: UdarVani — Voice-First Credit Ledger for Kirana Shops
- **One-line pitch**: Record credit (*udhaar*) sales in 5 seconds by speaking naturally in Hindi, Hinglish, or English—with zero typing and zero paid APIs.
- **Theme**: Livelihoods and Small Business
- **Prototype Stack**: React + TypeScript, FastAPI, SQLite, Browser Web Speech API, Docker Compose.

---

## Slide 2: The Problem
- Small Indian *kirana* (neighborhood grocery) shopkeepers handle peak-hour crowds solo, weighing items and packing bags simultaneously.
- Informal credit (*udhaar*) is essential for customer retention, yet recording it on paper slips or typing into multi-screen mobile apps during rush hours causes:
  - **Forgotten or unrecorded credit entries** (direct revenue leakage).
  - **Customer disputes** over quantities, unit prices, or same-name neighbors (e.g., two customers named *Ramesh*).
  - **High friction** for shopkeepers more comfortable speaking Hindi/Hinglish than typing English forms.

---

## Slide 3: The Solution — UdarVani
- **One dependable voice workflow**:
  1. **Listen**: Large, high-contrast microphone control (`hi-IN` / `en-IN`).
  2. **Extract & Correct**: Parses customer, item, quantity, and unit price—and replaces values immediately on spoken corrections (*"do doodh ke packet, nahi teen"* → `3 × ₹30 = ₹90`).
  3. **Clarify Ambiguity**: Detects duplicate customer names (*Ramesh Kumar — Dairy Gate* vs. *Ramesh Sharma — Station Road*) and missing unit prices before allowing a save.
  4. **Read Back & Confirm**: Reads back customer, quantity, and total aloud; writes to SQLite **only after explicit confirmation**. Cancelled drafts never touch the ledger.

---

## Slide 4: Intended Users & Audience Estimate
- **Primary Users**: Owner-operators of small, single-counter Indian *kirana*, dairy, and general stores managing recurring neighborhood *udhaar* accounts.
- **Approximate Audience Estimate (Explicit Assumptions)**:
  - **Macro Context**: Industry reports (e.g., BCG / Retailers Association of India / IBEF) commonly estimate **~12–13 million** *kirana* and traditional retail outlets across India.
  - **Target Segment Assumption**: Assuming ~40–50% are urban/semi-urban shops with an Android smartphone and recurring *udhaar* customers, the addressable base is **~5–6 million shopkeepers**.
  - **Initial Obtainable Pilot**: Focusing on 1–2 local retail clusters (50–100 shops per ward) requires no cloud onboarding or hardware beyond an existing smartphone/browser.
  - *Note: No user interviews or field surveys are claimed in this Round 2 prototype; pilot validation is the immediate next step.*

---

## Slide 5: Dependencies & Fallback Plans
- **Zero-Secret Local Core**: Runs via `docker compose up --build` with no API keys or paid cloud services.
- **Speech Recognition (`Web Speech API`)**:
  - *Risk*: Unsupported in some browsers (e.g., Firefox) or fails offline/in noisy shops.
  - *Fallback*: Built-in **Transcript Input** for immediate manual/accessibility entry + clear mic error recovery; Phase 2 roadmap adds an optional local `whisper.cpp` / `Vosk` Hindi sidecar for 100% offline speech-to-text.
- **Readback (`speechSynthesis`)**:
  - *Risk*: Missing system TTS voices on some devices.
  - *Fallback*: Room-legible visual status pills and high-contrast readback banner.
- **Storage (`SQLite`)**:
  - *Risk*: Single-device local file.
  - *Fallback*: Automated local export/backup; clean repository layer allows migration to PostgreSQL if multi-counter sync is needed later.

---

## Slide 6: Concrete Pilot & Growth Plan
- **Phase 1 — Local Shop Pilot (Weeks 1–4)**:
  - Shadow 5–10 neighborhood *kirana* shopkeepers during evening rush hours to measure real-world Hinglish phrasing, ambient noise accuracy, and correction frequency.
  - Expand the deterministic parser vocabulary with real local item names and regional units.
- **Phase 2 — Offline & Retention Features (Months 2–3)**:
  - Add offline-capable speech recognition fallback and one-tap WhatsApp/SMS *udhaar* summary sharing for customers.
  - Add daily backup export (CSV/PDF) for the shopkeeper.
- **Phase 3 — Sustainable Growth (Months 4+)**:
  - Keep core voice ledger **free** for small shopkeepers; monetize optionally via B2B wholesale/FMCG distributor ordering integrations or multi-staff sync for larger stores.
