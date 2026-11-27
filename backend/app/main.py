"""FastAPI application for UdarVani voice-first kirana ledger."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db, workflow
from .parser import SHOP_TZ


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize SQLite schema and seed data on startup."""
    db.init_db()
    yield


app = FastAPI(
    title="UdarVani API",
    description="Voice-first daily ledger and credit-recovery assistant for Indian kirana shops.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class VoiceProcessRequest(BaseModel):
    session_id: str = Field(default="default-shop-session", min_length=1, max_length=128)
    transcript: str = Field(..., min_length=1, max_length=1000)


class SelectCustomerRequest(BaseModel):
    session_id: str = Field(default="default-shop-session", min_length=1, max_length=128)
    customer_id: int = Field(..., ge=1)


class SessionActionRequest(BaseModel):
    session_id: str = Field(default="default-shop-session", min_length=1, max_length=128)


class ManualEntryRequest(BaseModel):
    payment_mode: str = Field(default="credit", pattern="^(cash|upi|credit|repayment)$")
    customer_id: int | None = None
    amount: float = Field(..., gt=0)
    item_name: str | None = None
    promised_date: str | None = None


class SettingsRequest(BaseModel):
    merchant_upi_id: str = Field(default="", max_length=120)


class RestockCreateRequest(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=120)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "udarvani-api"}


@app.get("/api/customers")
def get_customers(q: str | None = Query(default=None)) -> dict[str, object]:
    customers = db.list_customers(query=q)
    return {"customers": customers}


@app.get("/api/ledger")
def get_ledger(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
    entries = db.list_ledger_entries(limit=limit)
    local_today = datetime.now(SHOP_TZ).strftime("%Y-%m-%d")
    daily = db.get_daily_summary(local_today)
    return {
        "entries": entries,
        "count": len(entries),
        "total_credit": daily["credit_total"],
        "daily_summary": daily,
    }


@app.post("/api/ledger/manual")
def create_manual_entry(payload: ManualEntryRequest) -> dict[str, object]:
    """Record a manual Cash, UPI, Credit, or Repayment entry directly."""
    is_repay = payload.payment_mode == "repayment"
    mode = "credit" if is_repay else payload.payment_mode
    etype = "repayment" if is_repay else "direct_credit"
    if (mode == "credit" or is_repay) and not payload.customer_id:
        raise HTTPException(status_code=400, detail="Customer is required for credit or repayment.")

    paise = db.rupees_to_paise(payload.amount) or 0
    draft = {
        "session_id": f"manual-{datetime.now(SHOP_TZ).timestamp()}",
        "entry_type": etype,
        "payment_mode": mode,
        "customer_id": payload.customer_id,
        "total_amount": db.paise_to_rupees(paise),
        "amount_paise": paise,
        "promised_date": payload.promised_date or None,
        "heard_text": f"Manual {payload.payment_mode} ₹{payload.amount}",
    }
    entry, _ = db.commit_draft_to_ledger(draft, draft["session_id"])
    return {"entry": entry, "message": "Manual entry recorded."}


@app.get("/api/summary/daily")
def get_daily_summary_endpoint() -> dict[str, object]:
    local_today = datetime.now(SHOP_TZ).strftime("%Y-%m-%d")
    return db.get_daily_summary(local_today)


@app.get("/api/customers/{customer_id}/reminder")
def get_customer_reminder(customer_id: int) -> dict[str, object]:
    """Generate a polite reminder preview with optional UPI link if configured."""
    cust = db.get_customer_by_id(customer_id)
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found.")
    bal = db.get_customer_balance(customer_id)
    amount = max(0.0, float(bal["balance"]))
    amt_str = str(int(amount)) if amount.is_integer() else f"{amount:.2f}"
    upi_id = db.get_setting("merchant_upi_id", "")
    upi_link = ""
    if upi_id and "@" in upi_id and amount > 0:
        upi_link = f"upi://pay?pa={quote(upi_id)}&pn=UdarVani%20Kirana&am={amt_str}&cu=INR"

    message = (
        f"Namaste {cust['name']} ji, aapka kirana khata baki ₹{amt_str} hai. "
        f"Kripya suvidha anusar bhugtan karein."
    )
    if upi_link:
        message += f" UPI: {upi_link}"

    return {
        "customer": cust,
        "balance": amount,
        "upi_configured": bool(upi_link),
        "upi_link": upi_link,
        "message_preview": message,
        "whatsapp_url": f"https://wa.me/?text={quote(message)}",
        "sms_url": f"sms:?body={quote(message)}",
        "simulated_call_script": f"[Simulated Reminder Call] Namaste {cust['name']} ji, kirana store se bol rahe hain. Aapka ₹{amt_str} ka udhaar baki hai.",
    }


@app.get("/api/settings")
def read_settings() -> dict[str, str]:
    return {"merchant_upi_id": db.get_setting("merchant_upi_id", "")}


@app.post("/api/settings")
def update_settings(payload: SettingsRequest) -> dict[str, str]:
    db.set_setting("merchant_upi_id", payload.merchant_upi_id)
    return {"merchant_upi_id": db.get_setting("merchant_upi_id", "")}


@app.get("/api/restock")
def get_restock() -> dict[str, object]:
    return {"items": db.list_restock_items()}


@app.post("/api/restock")
def create_restock(payload: RestockCreateRequest) -> dict[str, object]:
    return {"item": db.add_restock_item(payload.item_name)}


@app.post("/api/restock/{item_id}/toggle")
def toggle_restock(item_id: int) -> dict[str, object]:
    item = db.toggle_restock_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Restock item not found.")
    return {"item": item}


@app.get("/api/draft")
def get_draft_state(session_id: str = Query(default="default-shop-session")) -> dict[str, object]:
    customers = db.list_customers()
    draft = db.get_draft(session_id)
    if draft and draft.get("status") == "cancelled":
        draft = None
    return workflow.build_state_response(draft, customers)


@app.post("/api/voice/process")
def process_voice(payload: VoiceProcessRequest) -> dict[str, object]:
    return workflow.process_voice_input(payload.session_id, payload.transcript)


@app.post("/api/draft/select-customer")
def select_customer(payload: SelectCustomerRequest) -> dict[str, object]:
    try:
        return workflow.select_customer_for_draft(payload.session_id, payload.customer_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/draft/confirm")
def confirm_draft(payload: SessionActionRequest) -> dict[str, object]:
    return workflow.confirm_draft(payload.session_id)


@app.post("/api/draft/cancel")
def cancel_draft(payload: SessionActionRequest) -> dict[str, object]:
    return workflow.cancel_draft(payload.session_id)
