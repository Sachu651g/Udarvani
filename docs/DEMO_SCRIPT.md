# UdarVani — Demo Video Script & Recording Checklist (< 3 Minutes)

**Target Platform**: YouTube (Public or Unlisted)  
**Target Length**: ~2 minutes 20 seconds (strictly under 3:00)  
**Theme**: Livelihoods and Small Business  

---

## Pre-Recording Checklist (What You Need to Record Personally)

- [ ] **Browser**: Open Google Chrome or Microsoft Edge on `http://localhost:3000` (Docker) or `http://localhost:5173` (local dev).
- [ ] **Microphone**: Ensure a working mic is connected and site permission is allowed for `localhost`.
- [ ] **Audio Output**: Keep speakers/headphone monitoring audible so the viewer hears the spoken readback (`speechSynthesis`).
- [ ] **Clean State**: Start with an empty or freshly reset ledger so the `₹90` entry stands out clearly.
- [ ] **Screen Recorder**: Record 1080p screen + microphone audio (e.g., OBS Studio, Loom, or Windows Snipping Tool / Xbox Game Bar).

---

## Shot-by-Shot Script

| Time | Shot / Screen State | Spoken / On-Screen Action | What the Viewer Sees |
| :--- | :--- | :--- | :--- |
| **0:00 – 0:20** | **Shot 1: Problem & Opening Screen** | **Narration**: *"In small Indian kirana shops, shopkeepers serve 3–4 customers at once and scribble credit sales—udhaar—on paper slips that get lost or miscalculated. This is UdarVani, a voice-first credit ledger built with React, FastAPI, and SQLite."* | Main UdarVani screen (`Ready` status pill, large mic button, empty Recent Credit Entries, Seeded Khata Accounts showing two *Ramesh* entries). |
| **0:20 – 0:55** | **Shot 2: Live Microphone Input + Spoken Correction** | **Tap `Tap & Speak Sale`** (status turns red: `Listening`).<br>**Speak into Mic**: *"Ramesh ke khate mein do doodh ke packet, nahi teen, tees rupaye ka ek."* | Live interim text appears, then settles into **Heard**, **Understood**, and a highlighted badge: `Corrected quantity: 2 → 3`. Calculation shows `3 × ₹30` and Total `₹90`. |
| **0:55 – 1:25** | **Shot 3: Duplicate-Name Clarification by Voice** | **Status**: `Clarification needed` (amber). Focus is on the two matching customers: *Ramesh Kumar (Dairy Gate)* and *Ramesh Sharma (Station Road)*.<br>**Tap `Tap & Speak Sale` and speak**: *"Dairy Gate wala"* | App resolves customer to **Ramesh Kumar (Dairy Gate / डेयरी गेट)**, switches status to `Awaiting confirmation`, and reads back aloud: *"Ramesh Kumar (Dairy Gate) ke khate mein 3 Doodh ke packet, 30 rupaye ke hisab se kul 90 rupaye. Save karein?"* |
| **1:25 – 1:50** | **Shot 4: Spoken Confirmation & Persistence** | **Tap `Tap & Speak Sale` and speak**: *"Haan, save kar do"*<br>Then **press Browser Refresh (`F5` / Reload)** to prove persistence. | Status turns green: `Saved`. Entry appears immediately in **Recent Credit Entries** (`Ramesh Kumar`, `3 × Doodh ke packet @ ₹30`, `₹90`). After page refresh, the `₹90` entry remains persisted from SQLite. |
| **1:50 – 2:15** | **Shot 5: Safety & Fallback Proof** | **Optional quick safety check**: Type *"Suresh ko do kilo chini"* in **Transcript Input** (showing missing price blocks saving), then click **Cancel Draft** (proving cancelled drafts never write to the ledger). | Demonstrates accessible fallback, missing-field guardrails, and zero-pollution cancellation. |
| **2:15 – 2:30** | **Shot 6: Closing** | **Narration**: *"UdarVani runs 100% locally with zero paid API keys—one `docker compose up --build` command. Thank you."* | Show `docker-compose.yml` or terminal briefly, or end on the clean persisted ledger screen. |

---

## Post-Recording Upload Checklist

- [ ] Watch the exported video end-to-end to confirm microphone audio, readback audio, and `3 × ₹30 = ₹90` text are clearly legible.
- [ ] Upload to YouTube as **Unlisted** or **Public**.
- [ ] Copy the exact YouTube URL into your Round 2 submission form.
