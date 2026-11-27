"""Comprehensive tests for UdarVani v2: draft switching, new customers, paise math, modes, dates, and recovery."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app


@pytest.fixture()
def test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "test_udarvani.db"
    monkeypatch.setenv("UDARVANI_DB_PATH", str(db_file))
    db.init_db(db_file)
    return db_file


def test_acceptance_draft_switch_new_customer_rajiv_and_reuse(test_db: Path) -> None:
    """
    Acceptance test:
    Leave an item draft incomplete, say 'राजीव ने तीस रुपये उधार लिए',
    confirm draft switch + new customer + save ₹30; then in a new session
    add ₹20 to 'Rajiv' and verify a single Rajiv account with ₹50.
    """
    with TestClient(app) as client:
        # 1. Incomplete item draft
        r0 = client.post("/api/voice/process", json={"session_id": "s_acc", "transcript": "Suresh ko 2 kilo chini"})
        assert r0.json()["draft"]["status"] == "clarification_needed"
        assert r0.json()["draft"]["clarification_field"] == "unit_price"

        # 2. New transaction arrives -> asks before replacing
        r1 = client.post("/api/voice/process", json={"session_id": "s_acc", "transcript": "राजीव ने तीस रुपये उधार लिए"})
        assert r1.json()["draft"]["clarification_field"] == "confirm_replace"

        # Test declining first -> preserves incomplete Suresh draft
        r_dec = client.post("/api/voice/process", json={"session_id": "s_acc", "transcript": "नहीं"})
        assert r_dec.json()["draft"]["item_name"] == "Chini"
        assert r_dec.json()["draft"]["clarification_field"] == "unit_price"

        # Re-send Rajiv ₹30 -> accept replacement -> asks to confirm new customer 'राजीव'
        client.post("/api/voice/process", json={"session_id": "s_acc", "transcript": "राजीव ने तीस रुपये उधार लिए"})
        r2 = client.post("/api/voice/process", json={"session_id": "s_acc", "transcript": "हाँ"})
        assert r2.json()["draft"]["clarification_field"] == "confirm_new_customer"
        assert r2.json()["draft"]["total_amount"] == 30

        # Confirm new customer -> awaiting_confirmation for ₹30 (never ₹12!)
        r3 = client.post("/api/voice/process", json={"session_id": "s_acc", "transcript": "हाँ"})
        assert r3.json()["draft"]["status"] == "awaiting_confirmation"
        assert r3.json()["draft"]["total_amount"] == 30
        rajiv_id = r3.json()["selected_customer"]["id"]

        # Confirm save
        r4 = client.post("/api/voice/process", json={"session_id": "s_acc", "transcript": "हाँ"})
        assert r4.json()["draft"]["status"] == "saved"
        assert r4.json()["last_saved_entry"]["total_amount"] == 30

        # 3. Second session using Romanized "Rajiv" reuses the exact same customer ID
        r5 = client.post("/api/voice/process", json={"session_id": "s_acc_2", "transcript": "Rajiv ne bees rupaye udhaar liye"})
        assert r5.json()["draft"]["status"] == "awaiting_confirmation"
        assert r5.json()["selected_customer"]["id"] == rajiv_id
        assert r5.json()["draft"]["total_amount"] == 20
        client.post("/api/voice/process", json={"session_id": "s_acc_2", "transcript": "हाँ"})

        # Check Rajiv balance = ₹50
        bal = client.post("/api/voice/process", json={"session_id": "s_bal", "transcript": "Rajiv ka kitna baaki hai?"}).json()
        assert bal["query_result"]["total"] == 50
        assert len([c for c in client.get("/api/customers").json()["customers"] if "rajiv" in c["name"].lower() or "राजीव" in c["name"]]) == 1


def test_cash_upi_repayment_and_daily_summary_excludes_repayments(test_db: Path) -> None:
    """Cash & UPI need no customer; repayment reduces balance and is excluded from sales_total."""
    with TestClient(app) as client:
        # Cash ₹200
        c1 = client.post("/api/voice/process", json={"session_id": "m1", "transcript": "200 rupaye cash sale"})
        assert c1.json()["draft"]["status"] == "awaiting_confirmation"
        assert c1.json()["draft"]["payment_mode"] == "cash"
        client.post("/api/draft/confirm", json={"session_id": "m1"})

        # UPI ₹150
        u1 = client.post("/api/voice/process", json={"session_id": "m2", "transcript": "150 rupaye UPI"})
        assert u1.json()["draft"]["status"] == "awaiting_confirmation"
        assert u1.json()["draft"]["payment_mode"] == "upi"
        client.post("/api/draft/confirm", json={"session_id": "m2"})

        # Manual credit ₹250 for Suresh Verma
        suresh = next(c for c in client.get("/api/customers").json()["customers"] if "Suresh" in c["name"])
        client.post("/api/ledger/manual", json={"payment_mode": "credit", "customer_id": suresh["id"], "amount": 250})

        # Repayment ₹100 from Suresh
        rep = client.post("/api/voice/process", json={"session_id": "m3", "transcript": "Suresh ne sau rupaye diye"})
        assert rep.json()["draft"]["entry_type"] == "repayment"
        assert rep.json()["draft"]["total_amount"] == 100
        client.post("/api/draft/confirm", json={"session_id": "m3"})

        # Daily summary: sales_total = 200 + 150 + 250 = 600 (excludes ₹100 repayment!)
        summary = client.post("/api/voice/process", json={"session_id": "m4", "transcript": "आज कितना उधार दिया?"}).json()
        qr = summary["query_result"]
        assert qr["total"] == 600
        assert qr["cash_total"] == 200
        assert qr["upi_total"] == 150
        assert qr["credit_total"] == 250
        assert qr["repayments_total"] == 100

        # Suresh balance = 250 - 100 = 150
        sbal = client.post("/api/voice/process", json={"session_id": "m4", "transcript": "Suresh ka kitna baaki hai?"}).json()
        assert sbal["query_result"]["total"] == 150


def test_compound_hindi_amount_and_promised_friday_date(test_db: Path) -> None:
    """'Ramesh Kumar ne do sau pachaas ka samaan liya, Friday ko denge' -> ₹250 + upcoming Friday."""
    with TestClient(app) as client:
        res = client.post(
            "/api/voice/process",
            json={"session_id": "p1", "transcript": "Ramesh Kumar ne do sau pachaas ka samaan liya, Friday ko denge"},
        )
        d = res.json()["draft"]
        assert d["status"] == "awaiting_confirmation"
        assert d["total_amount"] == 250
        assert d["promised_date"] is not None

        # Spoken date edit before saving
        res2 = client.post("/api/voice/process", json={"session_id": "p1", "transcript": "nahi Monday ko"})
        assert res2.json()["draft"]["promised_date"] != d["promised_date"]
        client.post("/api/draft/confirm", json={"session_id": "p1"})

        # Reminder preview without UPI configured
        ramesh_id = res.json()["selected_customer"]["id"]
        rem = client.get(f"/api/customers/{ramesh_id}/reminder").json()
        assert rem["balance"] == 250
        assert rem["upi_configured"] is False
        assert rem["upi_link"] == ""

        # Configure UPI and verify link appears
        client.post("/api/settings", json={"merchant_upi_id": "kirana@upi"})
        rem2 = client.get(f"/api/customers/{ramesh_id}/reminder").json()
        assert rem2["upi_configured"] is True
        assert "upi://pay?pa=kirana%40upi" in rem2["upi_link"]


def test_quantity_correction_and_reversal(test_db: Path) -> None:
    """Verify 2->3 quantity correction (₹90) and confirmed undo reversal."""
    with TestClient(app) as client:
        res = client.post(
            "/api/voice/process",
            json={"session_id": "q1", "transcript": "Ramesh Kumar ke khate mein do doodh ke packet, nahi teen, tees rupaye ka ek."},
        )
        d = res.json()["draft"]
        assert d["quantity"] == 3
        assert d["unit_price"] == 30
        assert d["total_amount"] == 90
        client.post("/api/draft/confirm", json={"session_id": "q1"})

        # Reverse last entry
        rev = client.post("/api/voice/process", json={"session_id": "q2", "transcript": "पिछली एंट्री वापस लो"})
        assert rev.json()["draft"]["entry_type"] == "reversal"
        client.post("/api/draft/confirm", json={"session_id": "q2"})
        # Duplicate confirm does not reverse twice
        client.post("/api/draft/confirm", json={"session_id": "q2"})
        assert client.get("/api/ledger").json()["count"] == 2
