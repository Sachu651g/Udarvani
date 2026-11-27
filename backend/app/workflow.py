"""Draft state machine, draft-switch & new-customer confirmation, queries, and readback."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import db
from .parser import (
    SHOP_TZ,
    ParseResult,
    is_new_transaction_utterance,
    match_customers,
    parse_utterance,
)

HINDI_NAME_MAP = {
    "Ramesh Kumar": "रमेश कुमार",
    "Ramesh Sharma": "रमेश शर्मा",
    "Suresh Verma": "सुरेश वर्मा",
    "Anita Devi": "अनीता देवी",
    "Mohan Lal": "मोहन लाल",
}

HINDI_AMOUNT_WORDS = {
    10: "दस", 20: "बीस", 30: "तीस", 40: "चालीस", 50: "पचास",
    60: "साठ", 70: "सत्तर", 80: "अस्सी", 90: "नब्बे", 100: "सौ",
}

# Lightweight Devanagari <-> Roman mapping for common Indian names (e.g. राजीव <-> rajiv)
DEVA_TO_LATIN = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ं": "n",
    "्": "",
}


def _approx_latin_aliases(name: str) -> list[str]:
    """Generate simple search aliases (e.g. 'राजीव' -> ['rajiv', 'rajeev']) without external APIs."""
    aliases = [name, name.lower()]
    if any("\u0900" <= ch <= "\u097f" for ch in name):
        out: list[str] = []
        for ch in name:
            out.append(DEVA_TO_LATIN.get(ch, ch))
        latin = "".join(out).strip()
        if latin:
            aliases.append(latin)
            aliases.append(latin.replace("v", "w"))
            aliases.append(latin.replace("i", "ee"))
    return list(dict.fromkeys(a for a in aliases if a))


def _fmt_num(val: float | None) -> str:
    if val is None:
        return "0"
    return str(int(val)) if float(val).is_integer() else f"{val:.2f}"


def _hindi_amount(val: float | None) -> str:
    if val is None:
        return "0"
    if float(val).is_integer() and int(val) in HINDI_AMOUNT_WORDS:
        return HINDI_AMOUNT_WORDS[int(val)]
    return _fmt_num(val)


def _hindi_name(name: str) -> str:
    return HINDI_NAME_MAP.get(name, name)


def _fmt_date_human(iso_date: str | None) -> str:
    if not iso_date:
        return ""
    try:
        d = date.fromisoformat(iso_date)
        return d.strftime("%A, %d %b")
    except Exception:
        return iso_date


def build_state_response(
    draft: dict[str, Any] | None,
    customers: list[dict[str, Any]],
    last_saved_entry: dict[str, Any] | None = None,
    readback_text: str = "",
    message: str = "",
    query_result: dict[str, Any] | None = None,
    end_voice_session: bool = False,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    selected_customer: dict[str, Any] | None = None

    if draft:
        cust_map = {c["id"]: c for c in customers}
        if draft.get("customer_id") and draft["customer_id"] in cust_map:
            selected_customer = cust_map[draft["customer_id"]]
        for cid in draft.get("candidate_customer_ids", []):
            if cid in cust_map:
                candidates.append(cust_map[cid])

    return {
        "draft": draft,
        "selected_customer": selected_customer,
        "candidate_customers": candidates,
        "last_saved_entry": last_saved_entry,
        "readback_text": readback_text,
        "message": message,
        "query_result": query_result,
        "end_voice_session": end_voice_session,
    }


def _evaluate_draft_state(
    draft: dict[str, Any],
    customers: list[dict[str, Any]],
) -> tuple[str, str, str, str]:
    cand_ids: list[int] = draft.get("candidate_customer_ids", [])
    cust_map = {c["id"]: c for c in customers}
    entry_type = draft.get("entry_type", "itemized_sale")
    payment_mode = draft.get("payment_mode", "credit")

    # 0A. Pending replacement confirmation
    if draft.get("pending_replacement"):
        prompt = "पिछला अधूरा ड्राफ्ट हटाकर नया ड्राफ्ट बनाएं? हाँ या नहीं बोलें।"
        return "clarification_needed", "confirm_replace", prompt, prompt

    # 0B. Pending new customer confirmation
    if draft.get("pending_new_customer"):
        cname = draft["pending_new_customer"]
        prompt = f"नया ग्राहक ‘{cname}’ जोड़ें? हाँ या नहीं बोलें।"
        return "clarification_needed", "confirm_new_customer", prompt, prompt

    # 1. Customer required for credit or repayment (not for cash/upi)
    needs_customer = (payment_mode == "credit") or (entry_type in {"repayment", "reversal"})
    if needs_customer:
        if not draft.get("customer_id") and len(cand_ids) > 1:
            options = " या ".join(
                f"{cust_map[cid]['name']} ({cust_map[cid]['label']})"
                for cid in cand_ids
                if cid in cust_map
            )
            prompt = f"कौन से {draft.get('customer_query') or 'ग्राहक'}? {options}?"
            return "clarification_needed", "customer_choice", prompt, prompt

        if not draft.get("customer_id"):
            prompt = "ग्राहक का नाम बताएं (जैसे रमेश कुमार या नया नाम)।"
            return "clarification_needed", "customer", prompt, prompt

    cust = cust_map.get(draft["customer_id"]) if draft.get("customer_id") else None
    cust_display = f"{cust['name']} ({cust['label']})" if cust else "Walk-in"
    cust_hi = _hindi_name(cust["name"]) if cust else "ग्राहक"

    # 2. Reversal confirmation
    if entry_type == "reversal":
        amt_str = _fmt_num(abs(float(draft.get("total_amount") or 0)))
        readback = f"{cust_hi} की पिछली {amt_str} रुपये की एंट्री वापस लें? पुष्टि के लिए हाँ बोलें।"
        return "awaiting_confirmation", "", "", readback

    # 3. Repayment confirmation
    if entry_type == "repayment":
        if draft.get("total_amount") is None or float(draft["total_amount"]) <= 0:
            prompt = f"{cust_hi} ने कितने रुपये जमा किए?"
            return "clarification_needed", "amount", prompt, prompt
        amt_str = _fmt_num(draft["total_amount"])
        readback = f"{cust_hi} से {amt_str} रुपये जमा (वापसी) दर्ज करें? हाँ या कन्फर्म बोलें।"
        return "awaiting_confirmation", "", "", readback

    # 4. Direct credit / Cash / UPI without items
    if entry_type == "direct_credit":
        if draft.get("total_amount") is None or float(draft["total_amount"]) <= 0:
            prompt = "कितने रुपये लिखने हैं?"
            return "clarification_needed", "amount", prompt, prompt
        amt_str = _fmt_num(draft["total_amount"])
        date_phrase = f", वादा तारीख {_fmt_date_human(draft.get('promised_date'))}" if draft.get("promised_date") else ""
        if payment_mode in {"cash", "upi"}:
            readback = f"{payment_mode.upper()} बिक्री {amt_str} रुपये सेव करें? हाँ बोलें।"
        else:
            readback = f"{cust_hi} के खाते में {amt_str} रुपये उधार{date_phrase} लिखें? हाँ या कन्फर्म बोलें।"
        return "awaiting_confirmation", "", "", readback

    # 5. Itemized sale checks
    if not draft.get("item_name"):
        prompt = f"{cust_display} के लिए कौन सा सामान लिखना है?"
        return "clarification_needed", "item_name", prompt, prompt

    if draft.get("quantity") is None or float(draft["quantity"]) <= 0:
        prompt = f"{draft['item_name']} की कितनी मात्रा लिखनी है?"
        return "clarification_needed", "quantity", prompt, prompt

    if draft.get("unit_price") is None or float(draft["unit_price"]) <= 0:
        qty_str = _fmt_num(draft["quantity"])
        unit = draft.get("unit_label") or "pcs"
        prompt = f"{cust_display} के लिए {qty_str} {unit} {draft['item_name']} का प्रति यूनिट दाम बताएं?"
        return "clarification_needed", "unit_price", prompt, prompt

    qty_str = _fmt_num(draft["quantity"])
    price_str = _fmt_num(draft["unit_price"])
    total_str = _fmt_num(draft["total_amount"])
    date_phrase = f", वादा तारीख {_fmt_date_human(draft.get('promised_date'))}" if draft.get("promised_date") else ""
    readback = (
        f"{cust_hi} के खाते में {qty_str} {draft['item_name']}, "
        f"{price_str} रुपये के हिसाब से कुल {total_str} रुपये{date_phrase}। सेव करें? हाँ बोलें।"
    )
    return "awaiting_confirmation", "", "", readback


def _new_empty_draft(session_id: str, entry_type: str = "itemized_sale", payment_mode: str = "credit") -> dict[str, Any]:
    return {
        "session_id": session_id,
        "status": "clarification_needed",
        "entry_type": entry_type,
        "payment_mode": payment_mode,
        "clarification_field": "",
        "customer_id": None,
        "customer_query": None,
        "candidate_customer_ids": [],
        "pending_new_customer": None,
        "pending_replacement": None,
        "item_name": None,
        "quantity": None,
        "unit_label": "pcs",
        "unit_price": None,
        "total_amount": None,
        "amount_paise": None,
        "promised_date": None,
        "reversal_target_id": None,
        "heard_text": "",
        "interpretation": "",
        "changed_fields": [],
        "clarification_prompt": "",
    }


def _apply_parsed_to_new_draft(
    session_id: str,
    parsed_dict: dict[str, Any],
    heard_text: str,
    customers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create a fresh draft from a parsed transaction dictionary (zero stale inheritance)."""
    etype = parsed_dict.get("entry_type") or "itemized_sale"
    pmode = parsed_dict.get("payment_mode") or "credit"
    draft = _new_empty_draft(session_id, entry_type=etype, payment_mode=pmode)
    draft["heard_text"] = heard_text
    draft["changed_fields"] = parsed_dict.get("changed_fields", [])
    draft["promised_date"] = parsed_dict.get("promised_date")

    cust_q = parsed_dict.get("customer_query")
    if cust_q:
        matches = match_customers(cust_q, customers)
        draft["customer_query"] = cust_q
        if len(matches) == 1:
            draft["customer_id"] = matches[0]["id"]
            draft["candidate_customer_ids"] = [matches[0]["id"]]
        elif len(matches) > 1:
            draft["customer_id"] = None
            draft["candidate_customer_ids"] = [m["id"] for m in matches]
        else:
            # New customer name -> ask before creating
            draft["pending_new_customer"] = cust_q

    if etype in {"direct_credit", "repayment"}:
        amt = parsed_dict.get("amount")
        if amt is not None:
            paise = db.rupees_to_paise(amt)
            draft["amount_paise"] = paise
            draft["total_amount"] = db.paise_to_rupees(paise)
    else:
        draft["item_name"] = parsed_dict.get("item_name")
        draft["quantity"] = parsed_dict.get("quantity")
        draft["unit_label"] = parsed_dict.get("unit_label") or "pcs"
        draft["unit_price"] = parsed_dict.get("unit_price")
        if draft["quantity"] is not None and draft["unit_price"] is not None:
            unit_paise = db.rupees_to_paise(draft["unit_price"]) or 0
            total_paise = int(round(float(draft["quantity"]) * unit_paise))
            draft["amount_paise"] = total_paise
            draft["total_amount"] = db.paise_to_rupees(total_paise)

    return draft


def _build_interpretation(draft: dict[str, Any], customers: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    etype = draft.get("entry_type", "itemized_sale")
    pmode = draft.get("payment_mode", "credit")
    if etype == "repayment":
        parts.append("Type: Repayment (जमा)")
    elif pmode in {"cash", "upi"}:
        parts.append(f"Mode: {pmode.upper()}")
    elif etype == "direct_credit":
        parts.append("Type: Direct Credit (उधार)")

    if draft.get("customer_id"):
        cust = next((c for c in customers if c["id"] == draft["customer_id"]), None)
        if cust:
            parts.append(f"Customer: {cust['name']} ({cust['label']})")
    elif draft.get("pending_new_customer"):
        parts.append(f"New customer: {draft['pending_new_customer']}")
    elif draft.get("candidate_customer_ids"):
        parts.append(f"Clarify: {len(draft['candidate_customer_ids'])} matches")

    if etype == "itemized_sale":
        if draft.get("item_name"):
            parts.append(f"Item: {draft['item_name']}")
        if draft.get("quantity") is not None:
            parts.append(f"Qty: {_fmt_num(draft['quantity'])} {draft.get('unit_label', 'pcs')}")
        if draft.get("unit_price") is not None:
            parts.append(f"Price: ₹{_fmt_num(draft['unit_price'])}")

    if draft.get("total_amount") is not None:
        parts.append(f"Amount: ₹{_fmt_num(draft['total_amount'])}")
    if draft.get("promised_date"):
        parts.append(f"Due: {_fmt_date_human(draft['promised_date'])}")
    return " | ".join(parts) if parts else "Listening for details."


def _compute_credit_advisor(bal: dict[str, Any], local_today: str) -> str:
    """Advisory-only suggestion based on balance and recorded delays (never modifies credit)."""
    entries = bal.get("entries", [])
    if len(entries) < 2:
        return "Credit Advisor: Too little history to assess risk."
    overdue_count = sum(
        1
        for e in entries
        if e.get("promised_date") and e["promised_date"] < local_today and e.get("reversed_by_id") is None
    )
    balance = float(bal.get("balance", 0))
    if balance <= 0:
        return "Credit Advisor: Balance settled (₹0). Safe for normal credit."
    if overdue_count >= 1:
        return f"Credit Advisor: {overdue_count} overdue promise(s) with ₹{_fmt_num(balance)} due — consider reminding before extending more credit."
    return f"Credit Advisor: ₹{_fmt_num(balance)} outstanding with no overdue dates recorded."


def process_voice_input(
    session_id: str,
    transcript: str,
    db_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Process a spoken or typed transcript against the current draft session."""
    customers = db.list_customers(db_path)
    current = db.get_draft(session_id, db_path)

    if current and current.get("status") in {"saved", "cancelled"}:
        db.delete_draft(session_id, db_path)
        current = None

    parsed = parse_utterance(transcript, customers, current, now=now)

    # --- 1. Read-only queries (end voice session cleanly) ---
    if parsed.intent == "query_today_total":
        local_today = (now or datetime.now(SHOP_TZ)).strftime("%Y-%m-%d")
        summary = db.get_daily_summary(local_today, db_path)
        overdue_names = ", ".join(
            f"{o['customer']['name']} (₹{_fmt_num(o['balance'])})" for o in summary["overdue_customers"]
        )
        overdue_speech = f" बकाया ओवरड्यू: {overdue_names}।" if overdue_names else ""
        readback = (
            f"आज कुल बिक्री ₹{_fmt_num(summary['sales_total'])} रही "
            f"(नगद ₹{_fmt_num(summary['cash_total'])}, UPI ₹{_fmt_num(summary['upi_total'])}, "
            f"उधार ₹{_fmt_num(summary['credit_total'])})। "
            f"वापसी प्राप्त: ₹{_fmt_num(summary['repayments_total'])}।{overdue_speech}"
        )
        return build_state_response(
            current,
            customers,
            readback_text=readback,
            message="Read-only daily summary.",
            end_voice_session=True,
            query_result={
                "kind": "today_total",
                "title": f"Daily Summary ({local_today})",
                "total": summary["sales_total"],
                "cash_total": summary["cash_total"],
                "upi_total": summary["upi_total"],
                "credit_total": summary["credit_total"],
                "repayments_total": summary["repayments_total"],
                "overdue_customers": summary["overdue_customers"],
                "count": summary["count"],
                "entries": summary["entries"],
                "note": "Today's sales total excludes repayments.",
            },
        )

    if parsed.intent == "query_customer_balance":
        if not parsed.customer_query:
            msg = "किस ग्राहक का बकाया देखना है? पूरा नाम बोलें।"
            return build_state_response(current, customers, readback_text=msg, message=msg)
        matches = match_customers(parsed.customer_query, customers)
        if len(matches) == 0:
            msg = f"‘{parsed.customer_query}’ नाम का कोई ग्राहक नहीं मिला।"
            return build_state_response(current, customers, readback_text=msg, message=msg, end_voice_session=True)
        if len(matches) > 1:
            opts = " या ".join(f"{m['name']} ({m['label']})" for m in matches)
            msg = f"किस {parsed.customer_query} का बकाया देखना है? {opts}?"
            return build_state_response(
                current,
                customers,
                readback_text=msg,
                message=msg,
                query_result={
                    "kind": "balance_ambiguous",
                    "title": "Specify Customer for Balance",
                    "candidates": matches,
                    "note": "Say full name to check recorded balance.",
                },
            )
        cust = matches[0]
        bal = db.get_customer_balance(cust["id"], db_path)
        local_today = (now or datetime.now(SHOP_TZ)).strftime("%Y-%m-%d")
        advisor = _compute_credit_advisor(bal, local_today)
        bal_str = _fmt_num(bal["balance"])
        cust_hi = _hindi_name(cust["name"])
        readback = f"{cust_hi} ({cust['label']}) का दर्ज बकाया {bal_str} रुपये है।"
        return build_state_response(
            current,
            customers,
            readback_text=readback,
            message="Read-only customer balance.",
            end_voice_session=True,
            query_result={
                "kind": "customer_balance",
                "title": f"{cust['name']} ({cust['label']}) — Recorded Balance",
                "customer": cust,
                "total": bal["balance"],
                "count": bal["count"],
                "entries": bal["entries"],
                "advisor_note": advisor,
                "note": "Recorded balance only (repayments outside this app are not included).",
            },
        )

    # --- 2. Restock list addition ---
    if parsed.intent == "add_restock" and parsed.restock_item:
        item = db.add_restock_item(parsed.restock_item, db_path)
        readback = f"{item['item_name']} को रीस्टॉक लिस्ट में जोड़ दिया गया।"
        return build_state_response(
            current,
            customers,
            readback_text=readback,
            message=f"Added '{item['item_name']}' to restock list.",
            end_voice_session=True,
        )

    # --- 3. Reversal request ---
    if parsed.intent == "reverse_last":
        target = db.get_last_reversible_entry(db_path)
        if not target:
            msg = "वापस लेने के लिए कोई हाल की एंट्री नहीं मिली।"
            return build_state_response(current, customers, readback_text=msg, message=msg, end_voice_session=True)
        draft = _new_empty_draft(session_id, entry_type="reversal", payment_mode=target.get("payment_mode", "credit"))
        draft["customer_id"] = target["customer_id"]
        draft["customer_query"] = target["customer_name"]
        draft["candidate_customer_ids"] = [target["customer_id"]] if target["customer_id"] else []
        draft["item_name"] = target["item_name"]
        p_abs = abs(int(target["amount_paise"] if target.get("amount_paise") is not None else (db.rupees_to_paise(target["total_amount"]) or 0)))
        draft["amount_paise"] = -p_abs
        draft["total_amount"] = db.paise_to_rupees(-p_abs)
        draft["reversal_target_id"] = target["id"]
        draft["heard_text"] = transcript.strip()
        status, clar_field, clar_prompt, readback = _evaluate_draft_state(draft, customers)
        draft["status"] = status
        draft["clarification_field"] = clar_field
        draft["clarification_prompt"] = clar_prompt
        draft["interpretation"] = f"Reverse Entry #{target['id']}: {target['customer_name']} — ₹{_fmt_num(target['total_amount'])}"
        saved_draft = db.upsert_draft(draft, db_path)
        return build_state_response(saved_draft, customers, readback_text=readback, message="Confirm reversal before saving.")

    # --- 4. Handle Confirm / Decline for pending_replacement or pending_new_customer ---
    if current and current.get("clarification_field") == "confirm_replace":
        if parsed.intent == "confirm" and current.get("pending_replacement"):
            rep = current["pending_replacement"]
            new_draft = _apply_parsed_to_new_draft(session_id, rep, rep.get("heard_text", transcript), customers)
            status, clar_field, clar_prompt, readback = _evaluate_draft_state(new_draft, customers)
            new_draft["status"] = status
            new_draft["clarification_field"] = clar_field
            new_draft["clarification_prompt"] = clar_prompt
            new_draft["interpretation"] = _build_interpretation(new_draft, customers)
            saved_draft = db.upsert_draft(new_draft, db_path)
            return build_state_response(saved_draft, customers, readback_text=readback, message="Switched to new draft.")
        if parsed.intent in {"decline", "cancel"}:
            current["pending_replacement"] = None
            status, clar_field, clar_prompt, readback = _evaluate_draft_state(current, customers)
            current["status"] = status
            current["clarification_field"] = clar_field
            current["clarification_prompt"] = clar_prompt
            saved_draft = db.upsert_draft(current, db_path)
            return build_state_response(saved_draft, customers, readback_text=readback, message="Preserved existing draft.")

    if current and current.get("clarification_field") == "confirm_new_customer":
        if parsed.intent == "confirm" and current.get("pending_new_customer"):
            new_name = current["pending_new_customer"]
            created = db.create_customer(new_name, label="Customer", aliases=_approx_latin_aliases(new_name), db_path=db_path)
            customers = db.list_customers(db_path)
            current["pending_new_customer"] = None
            current["customer_id"] = created["id"]
            current["customer_query"] = created["name"]
            current["candidate_customer_ids"] = [created["id"]]
            status, clar_field, clar_prompt, readback = _evaluate_draft_state(current, customers)
            current["status"] = status
            current["clarification_field"] = clar_field
            current["clarification_prompt"] = clar_prompt
            current["interpretation"] = _build_interpretation(current, customers)
            saved_draft = db.upsert_draft(current, db_path)
            return build_state_response(saved_draft, customers, readback_text=readback, message=f"Added customer {created['name']}.")
        if parsed.intent in {"decline", "cancel"}:
            current["pending_new_customer"] = None
            current["customer_query"] = None
            status, clar_field, clar_prompt, readback = _evaluate_draft_state(current, customers)
            current["status"] = status
            current["clarification_field"] = clar_field
            current["clarification_prompt"] = clar_prompt
            saved_draft = db.upsert_draft(current, db_path)
            return build_state_response(saved_draft, customers, readback_text=readback, message="New customer declined.")

    # --- 5. Standard Confirm / Cancel ---
    if parsed.intent == "confirm":
        if not current or current.get("status") != "awaiting_confirmation":
            prompt = current.get("clarification_prompt", "") if current else "अभी कोई ड्राफ्ट तैयार नहीं है।"
            return build_state_response(current, customers, readback_text=prompt, message="Draft is not ready for confirmation yet.")
        return confirm_draft(session_id, db_path)

    if parsed.intent == "cancel":
        return cancel_draft(session_id, db_path)

    # --- 6. Unclear reply ---
    if parsed.unclear_reply and current:
        current["heard_text"] = transcript.strip()
        retry_msg = f"‘{transcript.strip()}’ स्पष्ट नहीं हो पाया। {current.get('clarification_prompt') or 'कृपया दोबारा बोलें।'}"
        saved_draft = db.upsert_draft(current, db_path)
        return build_state_response(saved_draft, customers, readback_text=retry_msg, message="Reply unclear; please retry or type.")

    # --- 7. If unfinished draft exists and a brand-new transaction arrives -> ask once before replacing! ---
    if current and current.get("status") in {"clarification_needed", "awaiting_confirmation"} and is_new_transaction_utterance(parsed):
        rep_dict = parsed.to_dict()
        rep_dict["heard_text"] = transcript.strip()
        current["pending_replacement"] = rep_dict
        current["heard_text"] = transcript.strip()
        status, clar_field, clar_prompt, readback = _evaluate_draft_state(current, customers)
        current["status"] = status
        current["clarification_field"] = clar_field
        current["clarification_prompt"] = clar_prompt
        saved_draft = db.upsert_draft(current, db_path)
        return build_state_response(saved_draft, customers, readback_text=readback, message="Confirm replacing unfinished draft.")

    # --- 8. Patch existing draft OR create fresh draft ---
    if current is None:
        draft = _apply_parsed_to_new_draft(session_id, parsed.to_dict(), transcript.strip(), customers)
    else:
        draft = dict(current)
        draft["heard_text"] = transcript.strip()
        if parsed.changed_fields:
            draft["changed_fields"] = parsed.changed_fields

        if parsed.intent == "clarify_choice" and parsed.customer_query:
            cand_ids = draft.get("candidate_customer_ids", [])
            chosen = next((c for c in customers if c["id"] in cand_ids and c["name"] == parsed.customer_query), None)
            if chosen:
                draft["customer_id"] = chosen["id"]
                draft["customer_query"] = chosen["name"]
                draft["candidate_customer_ids"] = [chosen["id"]]
        elif parsed.intent == "patch_field":
            if parsed.promised_date:
                draft["promised_date"] = parsed.promised_date
            if parsed.amount is not None:
                paise = db.rupees_to_paise(parsed.amount)
                draft["amount_paise"] = paise
                draft["total_amount"] = db.paise_to_rupees(paise)
            if parsed.unit_price is not None:
                draft["unit_price"] = parsed.unit_price
                if draft.get("quantity") is not None:
                    total_p = int(round(float(draft["quantity"]) * (db.rupees_to_paise(parsed.unit_price) or 0)))
                    draft["amount_paise"] = total_p
                    draft["total_amount"] = db.paise_to_rupees(total_p)
        else:
            if parsed.customer_query:
                matches = match_customers(parsed.customer_query, customers)
                draft["customer_query"] = parsed.customer_query
                if len(matches) == 1:
                    draft["customer_id"] = matches[0]["id"]
                    draft["candidate_customer_ids"] = [matches[0]["id"]]
                    draft["pending_new_customer"] = None
                elif len(matches) > 1:
                    draft["customer_id"] = None
                    draft["candidate_customer_ids"] = [m["id"] for m in matches]
                    draft["pending_new_customer"] = None
                else:
                    draft["customer_id"] = None
                    draft["candidate_customer_ids"] = []
                    draft["pending_new_customer"] = parsed.customer_query
            if parsed.promised_date:
                draft["promised_date"] = parsed.promised_date
            if parsed.item_name and draft.get("entry_type") == "itemized_sale":
                draft["item_name"] = parsed.item_name
            if parsed.quantity is not None and draft.get("entry_type") == "itemized_sale":
                draft["quantity"] = parsed.quantity
            if parsed.unit_price is not None and draft.get("entry_type") == "itemized_sale":
                draft["unit_price"] = parsed.unit_price
            if draft.get("entry_type") == "itemized_sale" and draft.get("quantity") is not None and draft.get("unit_price") is not None:
                total_p = int(round(float(draft["quantity"]) * (db.rupees_to_paise(draft["unit_price"]) or 0)))
                draft["amount_paise"] = total_p
                draft["total_amount"] = db.paise_to_rupees(total_p)

    status, clar_field, clar_prompt, readback_text = _evaluate_draft_state(draft, customers)
    draft["status"] = status
    draft["clarification_field"] = clar_field
    draft["clarification_prompt"] = clar_prompt
    draft["interpretation"] = _build_interpretation(draft, customers)
    saved_draft = db.upsert_draft(draft, db_path)

    return build_state_response(saved_draft, customers, readback_text=readback_text, message="Draft updated.")


def select_customer_for_draft(
    session_id: str,
    customer_id: int,
    db_path: Path | None = None,
) -> dict[str, Any]:
    customers = db.list_customers(db_path)
    cust = db.get_customer_by_id(customer_id, db_path)
    if not cust:
        raise ValueError("Customer not found.")
    current = db.get_draft(session_id, db_path)
    if not current or current.get("status") in {"saved", "cancelled"}:
        raise ValueError("No active draft to update.")

    prev_query = current.get("customer_query") or "Ambiguous"
    current["customer_id"] = cust["id"]
    current["customer_query"] = cust["name"]
    current["candidate_customer_ids"] = [cust["id"]]
    current["pending_new_customer"] = None
    current["changed_fields"] = [{"field": "customer", "from": prev_query, "to": f"{cust['name']} ({cust['label']})"}]

    status, clar_field, clar_prompt, readback_text = _evaluate_draft_state(current, customers)
    current["status"] = status
    current["clarification_field"] = clar_field
    current["clarification_prompt"] = clar_prompt
    current["interpretation"] = _build_interpretation(current, customers)
    saved_draft = db.upsert_draft(current, db_path)
    return build_state_response(saved_draft, customers, readback_text=readback_text, message=f"Selected {cust['name']}.")


def confirm_draft(session_id: str, db_path: Path | None = None) -> dict[str, Any]:
    customers = db.list_customers(db_path)
    current = db.get_draft(session_id, db_path)
    if not current:
        return build_state_response(None, customers, readback_text="कोई सक्रिय ड्राफ्ट नहीं है।", message="No active draft to confirm.")

    # Button fallback for confirm_replace / confirm_new_customer
    if current.get("clarification_field") in {"confirm_replace", "confirm_new_customer"}:
        return process_voice_input(session_id, "हाँ", db_path)

    if current.get("status") == "saved":
        entries = db.list_ledger_entries(db_path, limit=1)
        return build_state_response(
            current,
            customers,
            last_saved_entry=entries[0] if entries else None,
            readback_text="यह एंट्री पहले ही सेव हो चुकी है।",
            message="Already saved (duplicate confirmation ignored).",
            end_voice_session=True,
        )

    if current.get("status") != "awaiting_confirmation":
        return build_state_response(
            current,
            customers,
            readback_text=current.get("clarification_prompt") or "पहले सभी जानकारी पूरी करें।",
            message="Draft requires clarification before saving.",
        )

    commit_key = f"{session_id}:{current['updated_at']}"
    entry, created_new = db.commit_draft_to_ledger(current, commit_key, db_path)

    current["status"] = "saved"
    current["clarification_field"] = ""
    current["clarification_prompt"] = ""
    saved_draft = db.upsert_draft(current, db_path)

    cust_hi = _hindi_name(entry["customer_name"])
    amt_word = _hindi_amount(abs(float(entry["total_amount"])))
    if entry.get("entry_type") == "reversal":
        readback = f"{cust_hi} की {amt_word} रुपये की एंट्री वापस ले ली गई।"
    elif entry.get("entry_type") == "repayment":
        readback = f"{cust_hi} से {amt_word} रुपये जमा दर्ज हो गए।"
    elif entry.get("payment_mode") in {"cash", "upi"}:
        readback = f"{entry['payment_mode'].upper()} बिक्री {amt_word} रुपये दर्ज हो गई।"
    else:
        readback = f"{cust_hi} के खाते में {amt_word} रुपये का उधार दर्ज हो गया"

    return build_state_response(
        saved_draft,
        customers,
        last_saved_entry=entry,
        readback_text=readback,
        message="Saved to ledger." if created_new else "Already saved.",
        end_voice_session=True,
    )


def cancel_draft(session_id: str, db_path: Path | None = None) -> dict[str, Any]:
    customers = db.list_customers(db_path)
    db.delete_draft(session_id, db_path)
    return build_state_response(
        None,
        customers,
        readback_text="ड्राफ्ट रद्द कर दिया गया। खाते में कुछ नहीं लिखा गया।",
        message="Draft cancelled. Nothing was written to the ledger.",
        end_voice_session=True,
    )
