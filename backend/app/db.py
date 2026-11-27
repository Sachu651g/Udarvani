"""SQLite database initialization, non-destructive migration, paise-exact storage, and persistence."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "udarvani.db"


def get_db_path() -> Path:
    """Return the configured SQLite database file path."""
    env_path = os.getenv("UDARVANI_DB_PATH")
    return Path(env_path) if env_path else DEFAULT_DB_PATH


def rupees_to_paise(amount: float | int | None) -> int | None:
    """Convert a rupee amount to exact integer paise."""
    if amount is None:
        return None
    return int(round(float(amount) * 100))


def paise_to_rupees(paise: int | None) -> float | None:
    """Convert integer paise to rupees rounded to 2 decimal places."""
    if paise is None:
        return None
    return round(paise / 100.0, 2)


@contextmanager
def get_connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection with row_factory enabled and foreign keys on."""
    target = db_path or get_db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SEED_CUSTOMERS = [
    ("Ramesh Kumar", "Dairy Gate / डेयरी गेट", "98xx-112", json.dumps(["रमेश", "रमेश कुमार", "डेयरी गेट", "dairy gate"], ensure_ascii=False)),
    ("Ramesh Sharma", "Station Road / स्टेशन रोड", "98xx-409", json.dumps(["रमेश", "रमेश शर्मा", "स्टेशन रोड", "station road"], ensure_ascii=False)),
    ("Suresh Verma", "Temple Lane / मंदिर गली", "98xx-231", json.dumps(["सुरेश", "सुरेश वर्मा", "मंदिर गली"], ensure_ascii=False)),
    ("Anita Devi", "School Chowk / स्कूल चौक", "98xx-518", json.dumps(["अनीता", "अनीता देवी", "स्कूल चौक"], ensure_ascii=False)),
    ("Mohan Lal", "Main Bazaar / मुख्य बाज़ार", "98xx-774", json.dumps(["मोहन", "मोहन लाल", "मुख्य बाज़ार"], ensure_ascii=False)),
]


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl_type: str) -> None:
    """Add a column to an existing SQLite table if missing (preserves existing data)."""
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


def init_db(db_path: Path | None = None) -> None:
    """Create tables if missing, migrate columns non-destructively, and seed customers."""
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                label TEXT NOT NULL,
                phone_hint TEXT NOT NULL,
                aliases TEXT NOT NULL DEFAULT '[]',
                UNIQUE(name, label)
            );

            CREATE TABLE IF NOT EXISTS shop_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS restock_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS draft_sessions (
                session_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                entry_type TEXT NOT NULL DEFAULT 'itemized_sale',
                payment_mode TEXT NOT NULL DEFAULT 'credit',
                clarification_field TEXT NOT NULL DEFAULT '',
                customer_id INTEGER,
                customer_query TEXT,
                candidate_customer_ids TEXT NOT NULL DEFAULT '[]',
                pending_new_customer TEXT,
                pending_replacement_json TEXT,
                item_name TEXT,
                quantity REAL,
                unit_label TEXT DEFAULT 'pcs',
                unit_price REAL,
                total_amount REAL,
                amount_paise INTEGER,
                promised_date TEXT,
                reversal_target_id INTEGER,
                heard_text TEXT NOT NULL DEFAULT '',
                interpretation TEXT NOT NULL DEFAULT '',
                changed_fields TEXT NOT NULL DEFAULT '[]',
                clarification_prompt TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS ledger_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE,
                entry_type TEXT NOT NULL DEFAULT 'itemized_sale',
                payment_mode TEXT NOT NULL DEFAULT 'credit',
                customer_id INTEGER,
                customer_name TEXT NOT NULL DEFAULT 'Walk-in Customer',
                customer_label TEXT NOT NULL DEFAULT '',
                item_name TEXT NOT NULL DEFAULT '',
                quantity REAL,
                unit_label TEXT NOT NULL DEFAULT 'pcs',
                unit_price REAL,
                total_amount REAL NOT NULL,
                amount_paise INTEGER,
                promised_date TEXT,
                reverses_entry_id INTEGER,
                reversed_by_id INTEGER,
                raw_transcript TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            """
        )

        # Non-destructive migrations for existing databases
        _ensure_column(conn, "customers", "aliases", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(conn, "draft_sessions", "entry_type", "TEXT NOT NULL DEFAULT 'itemized_sale'")
        _ensure_column(conn, "draft_sessions", "payment_mode", "TEXT NOT NULL DEFAULT 'credit'")
        _ensure_column(conn, "draft_sessions", "clarification_field", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "draft_sessions", "pending_new_customer", "TEXT")
        _ensure_column(conn, "draft_sessions", "pending_replacement_json", "TEXT")
        _ensure_column(conn, "draft_sessions", "amount_paise", "INTEGER")
        _ensure_column(conn, "draft_sessions", "promised_date", "TEXT")
        _ensure_column(conn, "draft_sessions", "reversal_target_id", "INTEGER")

        _ensure_column(conn, "ledger_entries", "entry_type", "TEXT NOT NULL DEFAULT 'itemized_sale'")
        _ensure_column(conn, "ledger_entries", "payment_mode", "TEXT NOT NULL DEFAULT 'credit'")
        _ensure_column(conn, "ledger_entries", "amount_paise", "INTEGER")
        _ensure_column(conn, "ledger_entries", "promised_date", "TEXT")
        _ensure_column(conn, "ledger_entries", "reverses_entry_id", "INTEGER")
        _ensure_column(conn, "ledger_entries", "reversed_by_id", "INTEGER")

        # If ledger_entries.customer_id was created as NOT NULL in an earlier version, migrate non-destructively
        cols_info = conn.execute("PRAGMA table_info(ledger_entries)").fetchall()
        cust_col = next((c for c in cols_info if c["name"] == "customer_id"), None)
        if cust_col and cust_col["notnull"] == 1:
            conn.executescript(
                """
                CREATE TABLE ledger_entries_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE,
                    entry_type TEXT NOT NULL DEFAULT 'itemized_sale',
                    payment_mode TEXT NOT NULL DEFAULT 'credit',
                    customer_id INTEGER,
                    customer_name TEXT NOT NULL DEFAULT 'Walk-in Customer',
                    customer_label TEXT NOT NULL DEFAULT '',
                    item_name TEXT NOT NULL DEFAULT '',
                    quantity REAL,
                    unit_label TEXT NOT NULL DEFAULT 'pcs',
                    unit_price REAL,
                    total_amount REAL NOT NULL,
                    amount_paise INTEGER,
                    promised_date TEXT,
                    reverses_entry_id INTEGER,
                    reversed_by_id INTEGER,
                    raw_transcript TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                INSERT INTO ledger_entries_v2 (
                    id, session_id, entry_type, payment_mode, customer_id, customer_name, customer_label,
                    item_name, quantity, unit_label, unit_price, total_amount, amount_paise,
                    promised_date, reverses_entry_id, reversed_by_id, raw_transcript, created_at
                )
                SELECT
                    id, session_id, entry_type, payment_mode, customer_id, customer_name, customer_label,
                    item_name, quantity, unit_label, unit_price, total_amount, amount_paise,
                    promised_date, reverses_entry_id, reversed_by_id, raw_transcript, created_at
                FROM ledger_entries;
                DROP TABLE ledger_entries;
                ALTER TABLE ledger_entries_v2 RENAME TO ledger_entries;
                """
            )

        existing_count = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        if existing_count == 0:
            conn.executemany(
                "INSERT INTO customers (name, label, phone_hint, aliases) VALUES (?, ?, ?, ?)",
                SEED_CUSTOMERS,
            )
        else:
            # Backfill aliases on seeded customers if empty
            for name, _label, _phone, aliases_json in SEED_CUSTOMERS:
                conn.execute(
                    "UPDATE customers SET aliases = ? WHERE name = ? AND (aliases IS NULL OR aliases = '[]')",
                    (aliases_json, name),
                )


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _row_to_customer(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    try:
        d["aliases"] = json.loads(d.get("aliases") or "[]")
    except Exception:
        d["aliases"] = []
    return d


def list_customers(db_path: Path | None = None, query: str | None = None) -> list[dict[str, Any]]:
    """Return all customers or filter by name/label/aliases substring."""
    with get_connection(db_path) as conn:
        if query and query.strip():
            like = f"%{query.strip()}%"
            rows = conn.execute(
                "SELECT id, name, label, phone_hint, aliases FROM customers "
                "WHERE name LIKE ? OR label LIKE ? OR aliases LIKE ? ORDER BY name, label",
                (like, like, like),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, name, label, phone_hint, aliases FROM customers ORDER BY name, label"
            ).fetchall()
        return [_row_to_customer(r) for r in rows]


def get_customer_by_id(customer_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    """Fetch a single customer by ID."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT id, name, label, phone_hint, aliases FROM customers WHERE id = ?",
            (customer_id,),
        ).fetchone()
        return _row_to_customer(row) if row else None


def create_customer(
    name: str,
    label: str = "New Account",
    phone_hint: str = "—",
    aliases: list[str] | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Create and persist a new customer with aliases, or return existing match."""
    clean_name = name.strip()
    alias_list = list(dict.fromkeys([clean_name, clean_name.lower()] + (aliases or [])))
    with get_connection(db_path) as conn:
        existing = conn.execute(
            "SELECT id, name, label, phone_hint, aliases FROM customers WHERE LOWER(name) = LOWER(?) AND label = ?",
            (clean_name, label),
        ).fetchone()
        if existing:
            return _row_to_customer(existing)
        cursor = conn.execute(
            "INSERT INTO customers (name, label, phone_hint, aliases) VALUES (?, ?, ?, ?)",
            (clean_name, label, phone_hint, json.dumps(alias_list, ensure_ascii=False)),
        )
        row = conn.execute(
            "SELECT id, name, label, phone_hint, aliases FROM customers WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return _row_to_customer(row)


def list_ledger_entries(db_path: Path | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Return confirmed ledger entries, newest first."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, session_id, entry_type, payment_mode, customer_id, customer_name, customer_label,
                   item_name, quantity, unit_label, unit_price, total_amount, amount_paise,
                   promised_date, reverses_entry_id, reversed_by_id, raw_transcript, created_at
            FROM ledger_entries
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_last_reversible_entry(db_path: Path | None = None) -> dict[str, Any] | None:
    """Return the most recent non-reversal, unreversed ledger entry."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM ledger_entries
            WHERE entry_type != 'reversal' AND reversed_by_id IS NULL
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None


def _signed_entry_paise(entry: dict[str, Any]) -> int:
    """Return signed paise contribution to customer credit balance (repayments reduce balance)."""
    paise = entry.get("amount_paise")
    if paise is None:
        paise = rupees_to_paise(entry.get("total_amount")) or 0
    if entry.get("entry_type") == "repayment":
        return -abs(int(paise))
    if entry.get("payment_mode") in {"cash", "upi"} and entry.get("entry_type") != "reversal":
        return 0
    return int(paise)


def get_customer_balance(customer_id: int, db_path: Path | None = None) -> dict[str, Any]:
    """Compute recorded credit balance (credit sales - repayments - reversals) for a customer."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, entry_type, payment_mode, customer_id, customer_name, customer_label,
                   item_name, quantity, unit_label, unit_price, total_amount, amount_paise,
                   promised_date, reverses_entry_id, reversed_by_id, created_at
            FROM ledger_entries
            WHERE customer_id = ?
            ORDER BY id DESC
            """,
            (customer_id,),
        ).fetchall()
        entries = [dict(r) for r in rows]
        balance_paise = sum(_signed_entry_paise(e) for e in entries)
        return {
            "entries": entries,
            "balance": paise_to_rupees(balance_paise) or 0.0,
            "balance_paise": balance_paise,
            "count": len(entries),
        }


def get_daily_summary(local_date_str: str, db_path: Path | None = None) -> dict[str, Any]:
    """Compute today's sales (excluding repayments), mode breakdown, repayments, and overdue customers."""
    all_entries = list_ledger_entries(db_path, limit=500)
    local_tz = datetime.now().astimezone().tzinfo
    today_entries: list[dict[str, Any]] = []

    for entry in all_entries:
        try:
            dt = datetime.fromisoformat(entry["created_at"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt.astimezone(local_tz).strftime("%Y-%m-%d") == local_date_str:
                today_entries.append(entry)
        except Exception:
            continue

    cash_paise = 0
    upi_paise = 0
    credit_paise = 0
    repayment_paise = 0

    for e in today_entries:
        p = e.get("amount_paise")
        if p is None:
            p = rupees_to_paise(e.get("total_amount")) or 0
        etype = e.get("entry_type", "itemized_sale")
        mode = e.get("payment_mode", "credit")

        if etype == "repayment":
            repayment_paise += abs(int(p))
        elif mode == "cash":
            cash_paise += int(p)
        elif mode == "upi":
            upi_paise += int(p)
        else:
            # credit sales + reversals of credit
            credit_paise += int(p)

    sales_total_paise = cash_paise + upi_paise + credit_paise

    # Overdue customers: promised_date < local_date_str and positive recorded balance
    overdue_map: dict[int, dict[str, Any]] = {}
    for c in list_customers(db_path):
        bal = get_customer_balance(c["id"], db_path)
        if bal["balance_paise"] <= 0:
            continue
        promised_dates = [
            e["promised_date"]
            for e in bal["entries"]
            if e.get("promised_date") and e.get("reversed_by_id") is None and e.get("entry_type") != "repayment"
        ]
        overdue_dates = [d for d in promised_dates if d < local_date_str]
        if overdue_dates:
            earliest = min(overdue_dates)
            overdue_map[c["id"]] = {
                "customer": c,
                "balance": bal["balance"],
                "promised_date": earliest,
            }

    overdue_customers = sorted(overdue_map.values(), key=lambda x: x["promised_date"])[:3]

    return {
        "date": local_date_str,
        "entries": today_entries,
        "count": len(today_entries),
        "sales_total": paise_to_rupees(sales_total_paise) or 0.0,
        "cash_total": paise_to_rupees(cash_paise) or 0.0,
        "upi_total": paise_to_rupees(upi_paise) or 0.0,
        "credit_total": paise_to_rupees(credit_paise) or 0.0,
        "repayments_total": paise_to_rupees(repayment_paise) or 0.0,
        "overdue_customers": overdue_customers,
    }


def get_draft(session_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    """Fetch the current draft session by session_id."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM draft_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["candidate_customer_ids"] = json.loads(data["candidate_customer_ids"] or "[]")
        data["changed_fields"] = json.loads(data["changed_fields"] or "[]")
        if data.get("pending_replacement_json"):
            data["pending_replacement"] = json.loads(data["pending_replacement_json"])
        else:
            data["pending_replacement"] = None
        return data


def upsert_draft(draft: dict[str, Any], db_path: Path | None = None) -> dict[str, Any]:
    """Insert or update a draft session."""
    pending_rep = draft.get("pending_replacement")
    pending_rep_json = json.dumps(pending_rep, ensure_ascii=False) if pending_rep else None
    amount_paise = draft.get("amount_paise")
    if amount_paise is None and draft.get("total_amount") is not None:
        amount_paise = rupees_to_paise(draft["total_amount"])

    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO draft_sessions (
                session_id, status, entry_type, payment_mode, clarification_field,
                customer_id, customer_query, candidate_customer_ids,
                pending_new_customer, pending_replacement_json,
                item_name, quantity, unit_label, unit_price, total_amount, amount_paise,
                promised_date, reversal_target_id, heard_text, interpretation,
                changed_fields, clarification_prompt, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                status = excluded.status,
                entry_type = excluded.entry_type,
                payment_mode = excluded.payment_mode,
                clarification_field = excluded.clarification_field,
                customer_id = excluded.customer_id,
                customer_query = excluded.customer_query,
                candidate_customer_ids = excluded.candidate_customer_ids,
                pending_new_customer = excluded.pending_new_customer,
                pending_replacement_json = excluded.pending_replacement_json,
                item_name = excluded.item_name,
                quantity = excluded.quantity,
                unit_label = excluded.unit_label,
                unit_price = excluded.unit_price,
                total_amount = excluded.total_amount,
                amount_paise = excluded.amount_paise,
                promised_date = excluded.promised_date,
                reversal_target_id = excluded.reversal_target_id,
                heard_text = excluded.heard_text,
                interpretation = excluded.interpretation,
                changed_fields = excluded.changed_fields,
                clarification_prompt = excluded.clarification_prompt,
                updated_at = excluded.updated_at
            """,
            (
                draft["session_id"],
                draft["status"],
                draft.get("entry_type", "itemized_sale"),
                draft.get("payment_mode", "credit"),
                draft.get("clarification_field", ""),
                draft.get("customer_id"),
                draft.get("customer_query"),
                json.dumps(draft.get("candidate_customer_ids", [])),
                draft.get("pending_new_customer"),
                pending_rep_json,
                draft.get("item_name"),
                draft.get("quantity"),
                draft.get("unit_label", "pcs"),
                draft.get("unit_price"),
                draft.get("total_amount"),
                amount_paise,
                draft.get("promised_date"),
                draft.get("reversal_target_id"),
                draft.get("heard_text", ""),
                draft.get("interpretation", ""),
                json.dumps(draft.get("changed_fields", [])),
                draft.get("clarification_prompt", ""),
                utc_now_iso(),
            ),
        )
    saved = get_draft(draft["session_id"], db_path)
    assert saved is not None
    return saved


def delete_draft(session_id: str, db_path: Path | None = None) -> None:
    """Remove an active draft session."""
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM draft_sessions WHERE session_id = ?", (session_id,))


def commit_draft_to_ledger(
    draft: dict[str, Any],
    commit_key: str,
    db_path: Path | None = None,
) -> tuple[dict[str, Any], bool]:
    """Persist a confirmed draft idempotently using integer paise arithmetic."""
    with get_connection(db_path) as conn:
        existing = conn.execute(
            "SELECT * FROM ledger_entries WHERE session_id = ?",
            (commit_key,),
        ).fetchone()
        if existing:
            return dict(existing), False

        entry_type = draft.get("entry_type", "itemized_sale")
        payment_mode = draft.get("payment_mode", "credit")

        if entry_type == "reversal":
            target_id = draft.get("reversal_target_id")
            if not target_id:
                raise ValueError("Missing reversal target entry.")
            target = conn.execute("SELECT * FROM ledger_entries WHERE id = ?", (target_id,)).fetchone()
            if not target:
                raise ValueError("Target entry for reversal not found.")
            if target["reversed_by_id"] is not None:
                existing_rev = conn.execute(
                    "SELECT * FROM ledger_entries WHERE id = ?", (target["reversed_by_id"],)
                ).fetchone()
                if existing_rev:
                    return dict(existing_rev), False

            now = utc_now_iso()
            target_paise = target["amount_paise"] if target["amount_paise"] is not None else rupees_to_paise(target["total_amount"])
            rev_paise = -int(target_paise or 0)
            rev_total = paise_to_rupees(rev_paise) or 0.0
            cursor = conn.execute(
                """
                INSERT INTO ledger_entries (
                    session_id, entry_type, payment_mode, customer_id, customer_name, customer_label,
                    item_name, quantity, unit_label, unit_price, total_amount, amount_paise,
                    reverses_entry_id, raw_transcript, created_at
                ) VALUES (?, 'reversal', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    commit_key,
                    target["payment_mode"] or "credit",
                    target["customer_id"],
                    target["customer_name"],
                    target["customer_label"],
                    f"Reversal: {target['item_name'] or 'Entry'}",
                    target["quantity"],
                    target["unit_label"],
                    target["unit_price"],
                    rev_total,
                    rev_paise,
                    target["id"],
                    draft.get("heard_text", ""),
                    now,
                ),
            )
            rev_id = cursor.lastrowid
            conn.execute("UPDATE ledger_entries SET reversed_by_id = ? WHERE id = ?", (rev_id, target["id"]))
            row = conn.execute("SELECT * FROM ledger_entries WHERE id = ?", (rev_id,)).fetchone()
            return dict(row), True

        customer_id = draft.get("customer_id")
        customer_name = "Walk-in Customer"
        customer_label = payment_mode.upper()
        if customer_id is not None:
            cust = conn.execute("SELECT id, name, label FROM customers WHERE id = ?", (customer_id,)).fetchone()
            if not cust:
                raise ValueError("Customer not found.")
            customer_name = cust["name"]
            customer_label = cust["label"]
        elif payment_mode == "credit" or entry_type == "repayment":
            raise ValueError("Cannot save credit or repayment without a valid customer.")

        now = utc_now_iso()
        if entry_type in {"direct_credit", "repayment"}:
            paise = draft.get("amount_paise") or rupees_to_paise(draft["total_amount"]) or 0
            total = paise_to_rupees(paise) or 0.0
            qty = 1.0
            unit_price = total
            item_name = "Repayment (जमा)" if entry_type == "repayment" else (
                f"{payment_mode.upper()} Sale" if payment_mode in {"cash", "upi"} else "Direct Credit (उधार)"
            )
            unit_label = entry_type
        else:
            qty = float(draft["quantity"])
            unit_price = float(draft["unit_price"])
            unit_paise = rupees_to_paise(unit_price) or 0
            paise = int(round(qty * unit_paise))
            total = paise_to_rupees(paise) or 0.0
            item_name = draft["item_name"]
            unit_label = draft.get("unit_label", "pcs")

        cursor = conn.execute(
            """
            INSERT INTO ledger_entries (
                session_id, entry_type, payment_mode, customer_id, customer_name, customer_label,
                item_name, quantity, unit_label, unit_price, total_amount, amount_paise,
                promised_date, raw_transcript, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                commit_key,
                entry_type,
                payment_mode,
                customer_id,
                customer_name,
                customer_label,
                item_name,
                qty,
                unit_label,
                unit_price,
                total,
                paise,
                draft.get("promised_date"),
                draft.get("heard_text", ""),
                now,
            ),
        )
        row = conn.execute("SELECT * FROM ledger_entries WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row), True


def get_setting(key: str, default: str = "", db_path: Path | None = None) -> str:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT value FROM shop_settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default


def set_setting(key: str, value: str, db_path: Path | None = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO shop_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value.strip()),
        )


def list_restock_items(db_path: Path | None = None) -> list[dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT id, item_name, done, created_at FROM restock_items ORDER BY done ASC, id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def add_restock_item(item_name: str, db_path: Path | None = None) -> dict[str, Any]:
    with get_connection(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO restock_items (item_name, done, created_at) VALUES (?, 0, ?)",
            (item_name.strip(), utc_now_iso()),
        )
        row = conn.execute("SELECT * FROM restock_items WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)


def toggle_restock_item(item_id: int, db_path: Path | None = None) -> dict[str, Any] | None:
    with get_connection(db_path) as conn:
        conn.execute("UPDATE restock_items SET done = CASE WHEN done = 0 THEN 1 ELSE 0 END WHERE id = ?", (item_id,))
        row = conn.execute("SELECT * FROM restock_items WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None
