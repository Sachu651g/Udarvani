"""Context-aware Hindi, Hinglish, and English voice-ledger parser for UdarVani."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    SHOP_TZ = ZoneInfo("Asia/Kolkata")
except ZoneInfoNotFoundError:
    SHOP_TZ = timezone(timedelta(hours=5, minutes=30), name="IST")

UNIT_NUMBERS: dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    # Hinglish / Romanized Hindi
    "ek": 1, "ik": 1, "do": 2, "teen": 3, "tin": 3, "chaar": 4, "char": 4,
    "paanch": 5, "panch": 5, "chhe": 6, "che": 6, "chhah": 6,
    "saat": 7, "sat": 7, "aath": 8, "ath": 8, "nau": 9,
    "das": 10, "gyarah": 11, "barah": 12, "terah": 13, "chaudah": 14,
    "pandrah": 15, "solah": 16, "satrah": 17, "atharah": 18, "unnees": 19,
    "bees": 20, "bis": 20, "ikkees": 21, "baees": 22, "pachees": 25, "pachis": 25,
    "tees": 30, "tis": 30, "chalees": 40, "chalis": 40, "paintalis": 45,
    "pachas": 50, "pachaas": 50, "pachpan": 55, "saath": 60, "sath": 60,
    "sattar": 70, "pachhattar": 75, "assi": 80, "nabbe": 90,
    "dedh": 150, "dhai": 250,
    # Devanagari Hindi
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
    "छह": 6, "छे": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
    "ग्यारह": 11, "बारह": 12, "पंद्रह": 15, "बीस": 20, "पच्चीस": 25,
    "तीस": 30, "चालीस": 40, "पैंतालीस": 45, "पचास": 50, "पचपन": 55,
    "साठ": 60, "सत्तर": 70, "पचहत्तर": 75, "अस्सी": 80, "नब्बे": 90,
    "डेढ़": 150, "ढाई": 250,
}

HUNDRED_WORDS = {"sau", "so", "hundred", "सौ"}
THOUSAND_WORDS = {"hazaar", "hajar", "thousand", "हज़ार", "हजार"}

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

CORRECTION_MARKERS = [
    "nahi", "nahin", "nhi", "नहीं", "नही",
    "actually", "sorry", "change to", "badal ke", "kar do", "kardo",
]

CONFIRM_PHRASES = {
    "haan", "ha", "han", "haan ji", "ha ji", "yes", "yep", "yeah",
    "confirm", "save", "save karo", "save kar do", "likh do", "theek hai",
    "thik hai", "pakka", "ok", "okay", "done", "chalo save",
    "हाँ", "हां", "जी हाँ", "ठीक है", "सेव करो", "सेव कर दो", "लिख दो", "पक्का",
    "कन्फर्म", "कन्फर्म करो", "दर्ज करो", "लिखो",
}

CANCEL_PHRASES = {
    "cancel", "cancel karo", "cancel kar do", "mat likho", "mat save karo",
    "ruko", "hatao", "reset", "chhodo", "band karo", "abort", "discard",
    "कैंसल", "रद्द", "रद्द करो", "मत लिखो", "हटाओ", "छोड़ो", "रुको",
}

DECLINE_PHRASES = {"no", "nahi", "nahin", "nhi", "mat", "नहीं", "नही", "मत"}

UNIT_NORMALIZATION: dict[str, str] = {
    "packet": "packet", "packets": "packet", "पैकेट": "packet",
    "kilo": "kg", "kg": "kg", "kgs": "kg", "किलो": "kg",
    "gram": "g", "gm": "g", "gms": "g", "ग्राम": "g",
    "liter": "L", "litre": "L", "liters": "L", "litres": "L", "लीटर": "L",
    "bottle": "bottle", "bottles": "bottle", "बोतल": "bottle",
    "dabba": "box", "dibba": "box", "डिब्बा": "box",
    "piece": "pcs", "pieces": "pcs", "pcs": "pcs", "पीस": "pcs",
    "bag": "bag", "bags": "bag", "थैला": "bag",
    "dozen": "dozen", "darjan": "dozen", "दर्जन": "dozen",
}

WEEKDAY_MAP: dict[str, int] = {
    "monday": 0, "mon": 0, "somwar": 0, "somvaar": 0, "सोमवार": 0,
    "tuesday": 1, "tue": 1, "mangalwar": 1, "mangalvaar": 1, "मंगलवार": 1,
    "wednesday": 2, "wed": 2, "budhwar": 2, "budhvaar": 2, "बुधवार": 2,
    "thursday": 3, "thu": 3, "guruwar": 3, "veerwar": 3, "गुरुवार": 3,
    "friday": 4, "fri": 4, "shukrawar": 4, "shukravaar": 4, "शुक्रवार": 4,
    "saturday": 5, "sat": 5, "shaniwar": 5, "shanivaar": 5, "शनिवार": 5,
    "sunday": 6, "sun": 6, "raviwar": 6, "ravivaar": 6, "रविवार": 6,
}

ITEM_STOPWORDS = {
    "ke", "ka", "ki", "ko", "ne", "mein", "me", "khate", "khata", "account", "liye",
    "liya", "diya", "diye", "ek", "rs", "rupaye", "rupees", "rupay", "rupaiye",
    "rupee", "inr", "nahi", "nahin", "actually", "sorry", "each", "per", "rate",
    "price", "daam", "aur", "and", "for", "of", "the", "a", "an", "to", "in", "on",
    "के", "का", "की", "को", "ने", "में", "खाते", "खाता", "रुपये", "रुपए", "रुपया",
    "नहीं", "लिए", "लिया", "दिया", "दिए", "उधार", "खरीद", "खरीदा", "खरीदे", "खरीदी",
    "kharida", "kharid", "kharide", "kar", "do", "kardo", "likh", "likho", "de", "dena",
    "udhaar", "udhar", "credit", "cash", "upi", "nagad", "नगद", "वाला", "वाली", "वाले",
    "wala", "wali", "samaan", "saaman", "सामान", "denge", "dega", "देंगे", "देगा",
}


@dataclass
class ParseResult:
    """Structured interpretation of a single voice or text utterance."""

    intent: str
    entry_type: str | None = None  # "direct_credit" | "itemized_sale" | "repayment"
    payment_mode: str = "credit"  # "credit" | "cash" | "upi"
    customer_query: str | None = None
    is_explicit_customer_phrase: bool = False
    item_name: str | None = None
    quantity: float | None = None
    unit_label: str | None = None
    unit_price: float | None = None
    amount: float | None = None
    promised_date: str | None = None
    ambiguous_date: bool = False
    restock_item: str | None = None
    changed_fields: list[dict[str, Any]] = field(default_factory=list)
    interpretation_notes: list[str] = field(default_factory=list)
    unclear_reply: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "entry_type": self.entry_type,
            "payment_mode": self.payment_mode,
            "customer_query": self.customer_query,
            "is_explicit_customer_phrase": self.is_explicit_customer_phrase,
            "item_name": self.item_name,
            "quantity": self.quantity,
            "unit_label": self.unit_label,
            "unit_price": self.unit_price,
            "amount": self.amount,
            "promised_date": self.promised_date,
            "ambiguous_date": self.ambiguous_date,
            "changed_fields": self.changed_fields,
            "interpretation_notes": self.interpretation_notes,
        }


def normalize_text(text: str) -> str:
    """Normalize Devanagari digits, currency symbols, and whitespace."""
    cleaned = text.translate(DEVANAGARI_DIGITS)
    cleaned = cleaned.replace("₹", " rs ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _strip_punct(text: str) -> str:
    return re.sub(r"[.,!?;:\"'।?]+", " ", text).strip()


def is_confirm_intent(text: str) -> bool:
    norm = re.sub(r"\s+", " ", _strip_punct(normalize_text(text).lower()))
    return norm in CONFIRM_PHRASES or norm in {"हाँ सही है", "हां सही है", "haan sahi hai", "yes save", "हाँ सेव करो", "हाँ सेव कर दो", "सही है"}


def is_decline_intent(text: str) -> bool:
    norm = re.sub(r"\s+", " ", _strip_punct(normalize_text(text).lower()))
    return norm in DECLINE_PHRASES


def is_cancel_intent(text: str) -> bool:
    norm = re.sub(r"\s+", " ", _strip_punct(normalize_text(text).lower()))
    if norm in CANCEL_PHRASES or norm in DECLINE_PHRASES:
        return True
    return any(norm.startswith(f"{p} ") or norm.endswith(f" {p}") for p in CANCEL_PHRASES if len(p) >= 4)


def _is_today_query(text: str) -> bool:
    norm = _strip_punct(normalize_text(text).lower())
    if norm in {"aaj ka hisab", "aaj ka hisaab", "आज का हिसाब", "daily summary", "evening summary", "शाम का हिसाब"}:
        return True
    return bool(
        re.search(r"(?:^|\s)(?:आज|aaj|today)(?=\s|$)", norm)
        and re.search(r"(?:^|\s)(?:कुल|कितना|कितनी|कितने|total|kitna|kitni|kitne|how much)(?=\s|$)", norm)
        and re.search(r"(?:^|\s)(?:बिक्री|उधार|sale|sales|credit|udhaar|udhar|कुल|total)(?=\s|$)", norm)
    )


def _is_balance_query(text: str) -> bool:
    norm = _strip_punct(normalize_text(text).lower())
    has_balance = re.search(r"(?:^|\s)(?:बकाया|बाकी|bakaya|baaki|baki|balance|hisab|hisaab|हिसाब)(?=\s|$)", norm)
    has_question = re.search(r"(?:^|\s)(?:कितना|कितनी|कितने|kitna|kitni|kitne|how much)(?=\s|$)", norm)
    has_credit = re.search(r"(?:^|\s)(?:उधार|udhaar|udhar|credit)(?=\s|$)", norm)
    return bool(has_balance or (has_question and has_credit))


def _is_reversal_request(text: str) -> bool:
    norm = _strip_punct(normalize_text(text).lower())
    return any(
        phrase in norm
        for phrase in (
            "पिछली एंट्री वापस", "पिछली एंट्री रद्द", "वापस लो",
            "pichli entry wapas", "pichhli entry wapas", "undo last", "reverse last",
        )
    )


def _extract_restock_item(text: str) -> str | None:
    norm = _strip_punct(normalize_text(text).lower())
    m = re.search(r"(?:restock\s+mein|restock\s+me|restock|रीस्टॉक\s+में)\s+(.+?)(?:\s+(?:likho|add|daalo|लिखो|डालो))?$", norm)
    if m and m.group(1).strip():
        return m.group(1).strip().title()
    if "khatam" in norm or "खत्म" in norm:
        cleaned = re.sub(r"\b(?:ho\s+gayi|ho\s+gaya|khatam|गई|गया|खत्म)\b", " ", norm).strip()
        if cleaned:
            return cleaned.title()
    return None


def extract_numbers_with_positions(segment: str) -> list[tuple[float, int, int, str]]:
    """
    Compositional Hindi/Hinglish/English number parser.

    Supports digits (250, 2.5), single words (तीस -> 30), and compound phrases
    like 'दो सौ पचास' -> 250, 'do sau pachaas' -> 250, 'एक सौ बीस' -> 120.
    """
    lower = normalize_text(segment).lower()
    tokens: list[tuple[str, int, int]] = [
        (m.group(0), m.start(), m.end()) for m in re.finditer(r"[^\s,।?!]+", lower)
    ]

    results: list[tuple[float, int, int, str]] = []
    i = 0
    while i < len(tokens):
        tok, s_pos, e_pos = tokens[i]

        # Numeric literal
        if re.fullmatch(r"-?\d+(?:\.\d+)?", tok):
            val = float(tok)
            # Check e.g. "2 sau"
            if i + 1 < len(tokens) and tokens[i + 1][0] in HUNDRED_WORDS:
                val *= 100
                e_pos = tokens[i + 1][2]
                i += 1
                if i + 1 < len(tokens) and tokens[i + 1][0] in UNIT_NUMBERS:
                    val += UNIT_NUMBERS[tokens[i + 1][0]]
                    e_pos = tokens[i + 1][2]
                    i += 1
            results.append((val, s_pos, e_pos, lower[s_pos:e_pos]))
            i += 1
            continue

        # Standalone "sau" / "सौ" = 100 (+ optional trailing units)
        if tok in HUNDRED_WORDS:
            val = 100.0
            if i + 1 < len(tokens) and tokens[i + 1][0] in UNIT_NUMBERS:
                val += UNIT_NUMBERS[tokens[i + 1][0]]
                e_pos = tokens[i + 1][2]
                i += 1
            results.append((val, s_pos, e_pos, lower[s_pos:e_pos]))
            i += 1
            continue

        # Unit word (possibly followed by sau/hazaar + trailing unit)
        if tok in UNIT_NUMBERS:
            val = float(UNIT_NUMBERS[tok])
            # "dedh sau" / "dhai sau" already 150/250
            if tok in {"dedh", "dhai", "डेढ़", "ढाई"} and i + 1 < len(tokens) and tokens[i + 1][0] in HUNDRED_WORDS:
                e_pos = tokens[i + 1][2]
                i += 1
                results.append((val, s_pos, e_pos, lower[s_pos:e_pos]))
                i += 1
                continue

            if i + 1 < len(tokens) and tokens[i + 1][0] in THOUSAND_WORDS:
                val *= 1000
                e_pos = tokens[i + 1][2]
                i += 1
                if i + 1 < len(tokens) and tokens[i + 1][0] in UNIT_NUMBERS:
                    next_u = float(UNIT_NUMBERS[tokens[i + 1][0]])
                    if i + 2 < len(tokens) and tokens[i + 2][0] in HUNDRED_WORDS:
                        val += next_u * 100
                        e_pos = tokens[i + 2][2]
                        i += 2
                    else:
                        val += next_u
                        e_pos = tokens[i + 1][2]
                        i += 1
            elif i + 1 < len(tokens) and tokens[i + 1][0] in HUNDRED_WORDS:
                val *= 100
                e_pos = tokens[i + 1][2]
                i += 1
                if i + 1 < len(tokens) and tokens[i + 1][0] in UNIT_NUMBERS:
                    val += UNIT_NUMBERS[tokens[i + 1][0]]
                    e_pos = tokens[i + 1][2]
                    i += 1

            results.append((val, s_pos, e_pos, lower[s_pos:e_pos]))
            i += 1
            continue

        i += 1

    # Filter out "ek"/"एक"/"1" in per-unit phrases like "rupaye ka ek"
    filtered: list[tuple[float, int, int, str]] = []
    for val, s, e, tok in results:
        if val == 1.0:
            prefix = lower[max(0, s - 6):s].strip()
            if re.search(r"(?:^|\s)(?:ka|ki|ke|per|का|की|के)$", prefix):
                continue
        filtered.append((val, s, e, tok))
    return filtered


def extract_promised_date(text: str, now: datetime | None = None) -> tuple[str | None, bool]:
    """
    Extract and resolve a promised payment date in shop timezone (Asia/Kolkata).

    Returns (YYYY-MM-DD | None, is_ambiguous).
    """
    ref = (now or datetime.now(SHOP_TZ)).date()
    norm = _strip_punct(normalize_text(text).lower())
    words = norm.split()

    if any(p in norm for p in ("agle hafte", "agla hafta", "baad mein", "agle mahine", "अगले हफ्ते", "बाद में")):
        return None, True

    if "kal" in words or "कल" in words or "tomorrow" in words:
        return (ref + timedelta(days=1)).isoformat(), False
    if "parso" in words or "परसों" in words:
        return (ref + timedelta(days=2)).isoformat(), False

    for w in words:
        if w in WEEKDAY_MAP:
            target_wd = WEEKDAY_MAP[w]
            days_ahead = (target_wd - ref.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (ref + timedelta(days=days_ahead)).isoformat(), False

    return None, False


def _split_correction_clauses(text: str) -> list[str]:
    pattern = re.compile(
        r"(?:,\s*)?\b(?:nahi|nahin|nhi|actually|sorry|नहीं|नही)\b",
        flags=re.IGNORECASE,
    )
    parts = [p.strip(" ,.") for p in pattern.split(text) if p.strip(" ,.")]
    return parts if parts else [text]


def _looks_like_price_context(clause: str, num_start: int, num_end: int) -> bool:
    tail = clause[num_end: num_end + 24].lower()
    head = clause[max(0, num_start - 14): num_start].lower()
    if re.match(
        r"^\s*(?:rs|₹|rupaye|rupay|rupaiye|rupees|rupee|रुपये|रुपए|रुपया|per|each)\b",
        tail,
    ):
        return True
    if re.search(r"(?:price|rate|daam|rs|₹|rupaye|rupees|रुपये|रुपए)\s*$", head):
        return True
    return False


def _extract_unit_label(text: str) -> str | None:
    lower = _strip_punct(normalize_text(text).lower())
    for token in lower.split():
        if token in UNIT_NORMALIZATION:
            return UNIT_NORMALIZATION[token]
    return None


def _customer_search_tokens(cust: dict[str, Any]) -> tuple[list[str], list[str]]:
    name_tokens = [t.lower() for t in cust["name"].split() if len(t) >= 2]
    label_tokens = [t.lower() for t in re.split(r"[\s/]+", cust["label"]) if len(t) >= 2]
    for alias in cust.get("aliases", []):
        for part in str(alias).lower().split():
            if part not in name_tokens and part not in label_tokens:
                name_tokens.append(part)
    return list(dict.fromkeys(name_tokens)), list(dict.fromkeys(label_tokens))


def match_customers(query: str, customers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Match a customer query against stored names, labels, and aliases."""
    q = _strip_punct(normalize_text(query).lower())
    if not q:
        return []

    stop = {"ke", "ka", "ki", "ko", "ne", "wala", "wali", "wale", "ji", "bhai", "saab", "वाला", "वाली", "वाले", "जी"}
    tokens = [t for t in q.split() if t not in stop]
    if not tokens:
        return []

    scored: list[tuple[int, dict[str, Any]]] = []
    for cust in customers:
        name_l = cust["name"].lower()
        aliases_l = [str(a).lower() for a in cust.get("aliases", [])]
        if q == name_l or q in aliases_l:
            scored.append((100, cust))
            continue

        name_toks, label_toks = _customer_search_tokens(cust)
        score = 0
        for tok in tokens:
            if len(tok) < 2:
                continue
            if tok in name_toks:
                score += 10
            elif tok in label_toks:
                score += 8

        if score > 0:
            scored.append((score, cust))

    if not scored:
        return []

    max_score = max(s for s, _ in scored)
    return [c for s, c in scored if s == max_score]


def resolve_clarification_choice(
    transcript: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    norm = _strip_punct(normalize_text(transcript).lower())
    words = norm.split()

    first_markers = {"first", "1", "one", "pehle", "pehla", "pahla", "ek", "पहला", "पहले"}
    second_markers = {"second", "2", "two", "doosra", "dusra", "doosre", "do", "दूसरा", "दूसरे"}
    has_specific = any(tok in norm for tok in ("sharma", "station", "kumar", "dairy", "शर्मा", "स्टेशन", "कुमार", "डेयरी"))
    if not has_specific:
        if len(candidates) >= 1 and (norm in first_markers or any(w in first_markers for w in words)):
            return candidates[0]
        if len(candidates) >= 2 and (norm in second_markers or any(w in second_markers for w in words)):
            return candidates[1]

    matches = match_customers(transcript, candidates)
    if len(matches) == 1:
        return matches[0]
    return None


def _extract_customer_phrase(text: str, customers: list[dict[str, Any]]) -> tuple[str | None, bool]:
    """
    Extract customer name/alias from utterance.

    Returns (customer_query, is_explicit_prefix). Supports both stored and new names.
    """
    norm = _strip_punct(normalize_text(text))
    norm = re.sub(r"^(?:(?:आज|aaj|today|please|कृपया)\s+)+", "", norm, flags=re.IGNORECASE)
    norm_l = norm.lower()

    # 1. Explicit "<name> ne/ko/ke khate/ke liye" prefix (use lookahead for whitespace/end so Devanagari vowel signs match)
    m = re.match(
        r"^(.+?)\s+(?:ke\s+khate|ka\s+khata|ke\s+liye|ka|ko|ne|के\s+खाते|का\s+खाता|का|के\s+लिए|को|ने)(?=\s|$)",
        norm,
        flags=re.IGNORECASE,
    )
    if m:
        candidate_q = m.group(1).strip()
        cand_l = candidate_q.lower()
        # Ignore non-customer prefixes like "cash sale" / "aaj"
        if cand_l not in {"cash", "upi", "gpay", "phonepe", "aaj", "today", "आज", "नगद"} and not re.fullmatch(r"\d+", cand_l):
            return candidate_q, True

    # 2. Scan for any known stored customer name/alias token
    words = norm_l.split()
    for cust in customers:
        name_toks, label_toks = _customer_search_tokens(cust)
        matched_name = [t for t in name_toks if t in words]
        if matched_name:
            matched_label = [t for t in label_toks if t in words]
            return " ".join(matched_name + matched_label), False

    return None, False


def _detect_payment_mode(text: str) -> str:
    norm = _strip_punct(normalize_text(text).lower())
    words = set(norm.split())
    if words & {"upi", "gpay", "phonepe", "paytm", "यूपीआई", "जीपे"}:
        return "upi"
    if words & {"cash", "nagad", "नगद", "कैश"}:
        return "cash"
    return "credit"


def _is_repayment_utterance(text: str, unit_label: str | None) -> bool:
    if unit_label:
        return False
    norm = _strip_punct(normalize_text(text).lower())
    words = set(norm.split())
    repay_verbs = {"diye", "diya", "jama", "paid", "returned", "दिए", "दिया", "जमा", "वापस"}
    credit_markers = {"उधार", "udhaar", "udhar", "credit"}
    return bool(words & repay_verbs) and not bool(words & credit_markers)


def _is_direct_credit_or_total_utterance(text: str, unit_label: str | None) -> bool:
    if unit_label:
        return False
    norm = _strip_punct(normalize_text(text).lower())
    if any(w in norm for w in ("samaan", "saaman", "सामान")):
        return True
    has_sale_verb = any(w in norm for w in ("खरीद", "खरीदा", "खरीदे", "खरीदी", "kharid", "kharida", "packet", "पैकेट"))
    if has_sale_verb:
        return False
    credit_markers = ("उधार", "udhaar", "udhar", "लिए", "liye", "liya", "bakaya", "बकाया")
    return any(c in norm for c in credit_markers)


def _extract_item_name(
    text: str,
    customer_query: str | None,
    customers: list[dict[str, Any]],
) -> str | None:
    cleaned = normalize_text(text)

    cleaned = re.sub(
        r"^.+?(?:ke\s+khate\s+mein|ke\s+khate\s+me|ka\s+khata|ke\s+liye|ka|ko|ne|के\s+खाते\s+में|का\s+खाता|के\s+लिए|को|ने)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    if customer_query:
        for tok in customer_query.lower().split():
            cleaned = re.sub(rf"(?<!\w){re.escape(tok)}(?!\w)", " ", cleaned, flags=re.IGNORECASE)

    for cust in customers:
        name_toks, _ = _customer_search_tokens(cust)
        for part in name_toks:
            if len(part) > 2:
                cleaned = re.sub(rf"(?<!\w){re.escape(part)}(?!\w)", " ", cleaned, flags=re.IGNORECASE)

    # Remove weekday/date phrases
    for wd in list(WEEKDAY_MAP.keys()) + ["kal", "parso", "tomorrow", "कल", "परसों"]:
        cleaned = re.sub(rf"(?<!\w){re.escape(wd)}(?!\w)", " ", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(
        r"(?:,\s*)?(?:\S+\s+){0,2}(?:rs|₹|rupaye|rupay|rupaiye|rupees|rupee|रुपये|रुपए|रुपया)\b(?:\s+(?:ka|ki|ke|per|each|ek|एक|का|की|के)){0,3}",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    for marker in CORRECTION_MARKERS:
        cleaned = re.sub(rf"(?<!\w){re.escape(marker)}(?!\w)", " ", cleaned, flags=re.IGNORECASE)

    for w in sorted(list(UNIT_NUMBERS.keys()) + list(HUNDRED_WORDS) + list(THOUSAND_WORDS), key=len, reverse=True):
        if w == "no":
            continue
        cleaned = re.sub(rf"(?<!\w){re.escape(w)}(?!\w)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+(?:\.\d+)?\b", " ", cleaned)

    for unit_tok in UNIT_NORMALIZATION:
        cleaned = re.sub(rf"(?<!\w){re.escape(unit_tok)}(?!\w)", " ", cleaned, flags=re.IGNORECASE)

    cleaned = _strip_punct(cleaned)
    tokens = cleaned.split()
    while tokens and tokens[0].lower() in ITEM_STOPWORDS:
        tokens.pop(0)
    while tokens and tokens[-1].lower() in ITEM_STOPWORDS:
        tokens.pop()

    result = " ".join(tokens).strip()
    if not result:
        return None
    return result[0].upper() + result[1:] if result[0].isascii() else result


def is_new_transaction_utterance(parsed: ParseResult) -> bool:
    """Return True if `parsed` represents a brand-new standalone transaction rather than a short reply."""
    if parsed.intent != "upsert":
        return False
    has_amount_or_item = (parsed.entry_type == "direct_credit" and parsed.is_explicit_customer_phrase) or (parsed.amount is not None) or (parsed.item_name is not None) or (parsed.quantity is not None)
    has_actor_or_mode = (parsed.customer_query is not None) or (parsed.payment_mode in {"cash", "upi"}) or (parsed.entry_type == "repayment")
    return has_amount_or_item and has_actor_or_mode


def parse_utterance(
    transcript: str,
    customers: list[dict[str, Any]],
    current_draft: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> ParseResult:
    """Classify and parse a spoken/typed transcript."""
    raw = transcript.strip()
    if not raw:
        return ParseResult(intent="upsert")

    # 1. Read-only queries & utility commands ALWAYS classify first
    explicit_balance = re.match(r"^(?:balance for|balance of)\s+(.+?)[?।]*$", raw, re.I)
    if explicit_balance:
        return ParseResult(intent="query_customer_balance", customer_query=explicit_balance.group(1))
    cust_q, _ = _extract_customer_phrase(normalize_text(raw), customers)
    if _is_balance_query(raw) and cust_q and cust_q.lower() not in {"what", "how much", "आज", "today"}:
        return ParseResult(intent="query_customer_balance", customer_query=cust_q)
    if _is_today_query(raw):
        return ParseResult(intent="query_today_total")
    if _is_balance_query(raw):
        return ParseResult(intent="query_customer_balance")
    if _is_reversal_request(raw):
        return ParseResult(intent="reverse_last")

    restock_item = _extract_restock_item(raw)
    if restock_item and ("restock" in raw.lower() or "रीस्टॉक" in raw.lower() or "खत्म" in raw.lower() or "khatam" in raw.lower()):
        return ParseResult(intent="add_restock", restock_item=restock_item)

    clar_field = current_draft.get("clarification_field", "") if current_draft else ""

    # 2. Confirm / Decline / Cancel on active draft
    if current_draft and current_draft.get("status") in {"awaiting_confirmation", "clarification_needed"}:
        if clar_field in {"confirm_replace", "confirm_new_customer"}:
            if is_confirm_intent(raw):
                return ParseResult(intent="confirm")
            if is_decline_intent(raw):
                return ParseResult(intent="decline")
        if is_confirm_intent(raw):
            return ParseResult(intent="confirm")
        if is_cancel_intent(raw):
            return ParseResult(intent="cancel")

    # 3. Parse full utterance first so a new transaction is NEVER swallowed as a short reply
    normalized = normalize_text(raw)
    if re.match(r"^(?:क्या|कौन|कितना|कितनी|कितने|what|how many|how much|kitna|kitni|kitne)(?=\s|$)", normalized.lower()):
        return ParseResult(intent="clarify_question")
    customer_query, is_explicit_prefix = _extract_customer_phrase(normalized, customers)
    unit_label = _extract_unit_label(normalized)
    payment_mode = _detect_payment_mode(normalized)
    promised_date, ambiguous_date = extract_promised_date(normalized, now)

    # Check if this is a full new transaction
    nums_all = extract_numbers_with_positions(normalized)
    looks_like_full_new_tx = (
        (customer_query is not None and (bool(nums_all) or
         (is_explicit_prefix and _is_direct_credit_or_total_utterance(normalized, unit_label))))
        or (payment_mode in {"cash", "upi"} and len(nums_all) >= 1)
    )

    # 4. Short replies for active clarification (only when NOT a full new transaction)
    if current_draft and current_draft.get("status") == "awaiting_confirmation" and clar_field == "" and current_draft.get("entry_type") in {"direct_credit", "repayment"}:
        if re.match(r"^(?:नहीं|नही|nahi|badlo|बदलो|amount|रकम|change)(?:\s|$)", normalized.lower()) and len(nums_all) == 1:
            return ParseResult(intent="patch_field", amount=nums_all[0][0])

    if current_draft and current_draft.get("status") == "clarification_needed" and not looks_like_full_new_tx:
        if clar_field == "customer_choice" and len(current_draft.get("candidate_customer_ids", [])) > 1:
            cand_ids = set(current_draft["candidate_customer_ids"])
            candidates = [c for c in customers if c["id"] in cand_ids]
            chosen = resolve_clarification_choice(raw, candidates)
            if chosen:
                return ParseResult(
                    intent="clarify_choice",
                    customer_query=chosen["name"],
                    changed_fields=[{
                        "field": "customer",
                        "from": current_draft.get("customer_query") or "Ambiguous",
                        "to": f"{chosen['name']} ({chosen['label']})",
                    }],
                    interpretation_notes=[f"Selected customer: {chosen['name']} ({chosen['label']})"],
                )
            return ParseResult(intent="upsert", unclear_reply=True)

        if clar_field == "customer":
            name_only = _strip_punct(normalized)
            if name_only and not nums_all and len(name_only.split()) <= 4 and not re.search(r"उधार|udhaa?r|रुप|rupee|लिख|कितन|price|save", name_only, re.I):
                return ParseResult(
                    intent="upsert",
                    customer_query=customer_query or name_only,
                    is_explicit_customer_phrase=True,
                )
            return ParseResult(intent="upsert", unclear_reply=True)

        if clar_field == "promised_date":
            if promised_date:
                return ParseResult(
                    intent="patch_field",
                    promised_date=promised_date,
                    changed_fields=[{"field": "promised_date", "from": current_draft.get("promised_date"), "to": promised_date}],
                )
            return ParseResult(intent="upsert", unclear_reply=True)

        if clar_field in {"unit_price", "amount"}:
            if len(nums_all) != 1 or not re.fullmatch(
                r"(?:(?:amount|price|rate|रकम|दाम|नहीं|badlo)\s+)?(?:(?:rs|inr)\s+)?"
                + re.escape(nums_all[0][3])
                + r"(?:\s+(?:रुपये|रुपए|रुपया|rupaye|rupees|rs|inr|each|per unit))?[.!।]?",
                normalized.lower(),
            ):
                return ParseResult(intent="upsert", unclear_reply=True)
            val = nums_all[0][0]
            if clar_field == "amount":
                return ParseResult(intent="patch_field", amount=val)
            return ParseResult(intent="patch_field", unit_price=val)

    # 5. Inline date edit while awaiting confirmation (e.g. "nahi Monday ko")
    if current_draft and current_draft.get("status") == "awaiting_confirmation" and promised_date and not nums_all:
        return ParseResult(
            intent="patch_field",
            promised_date=promised_date,
            changed_fields=[{"field": "promised_date", "from": current_draft.get("promised_date"), "to": promised_date}],
        )

    # 6. Repayment ("Ramesh ne sau rupaye diye")
    if _is_repayment_utterance(normalized, unit_label) and nums_all:
        amount = nums_all[-1][0]
        return ParseResult(
            intent="upsert",
            entry_type="repayment",
            payment_mode="credit",
            customer_query=customer_query,
            is_explicit_customer_phrase=is_explicit_prefix,
            amount=amount,
            interpretation_notes=[f"Repayment (जमा): ₹{_fmt_num(amount)}"],
        )

    # 7. Cash or UPI sale without items ("200 rupaye cash sale", "150 UPI")
    if payment_mode in {"cash", "upi"} and not unit_label and nums_all:
        amount = nums_all[-1][0]
        return ParseResult(
            intent="upsert",
            entry_type="direct_credit",
            payment_mode=payment_mode,
            customer_query=customer_query,
            is_explicit_customer_phrase=is_explicit_prefix,
            amount=amount,
            interpretation_notes=[f"{payment_mode.upper()} Sale: ₹{_fmt_num(amount)}"],
        )

    # 8. Direct credit ("रमेश ने तीस रुपये उधार लिए" or "Ramesh ne do sau pachaas ka samaan liya, Friday ko denge")
    if _is_direct_credit_or_total_utterance(normalized, unit_label):
        # A date day number is not the amount. Prefer the currency number; otherwise
        # accept only one number per clause, with an explicit correction between clauses.
        currency = r"\s*(?:रुपये|रुपए|रुपया|rupaye|rupees|rupee|rs|inr)(?=\s|$|[,.।])"
        monetary = [n for n in nums_all if re.match(currency, normalized.lower()[n[2]:])
                    or re.search(r"(?:^|\s)(?:rs|inr)\s*$", normalized.lower()[:n[1]])]
        choice = monetary or nums_all
        if len(choice) > 1 and len(_split_correction_clauses(normalized)) == 1:
            choice = []
        amount = choice[-1][0] if choice else None
        changed: list[dict[str, Any]] = []
        notes: list[str] = ["Direct credit (उधार)"]
        if len(choice) > 1:
            changed.append({"field": "amount", "from": choice[0][0], "to": amount})
            notes.append(f"Amount corrected: ₹{_fmt_num(choice[0][0])} → ₹{_fmt_num(amount)}")
        return ParseResult(
            intent="upsert",
            entry_type="direct_credit",
            payment_mode=payment_mode,
            customer_query=customer_query,
            is_explicit_customer_phrase=is_explicit_prefix,
            amount=amount,
            promised_date=promised_date,
            ambiguous_date=ambiguous_date,
            changed_fields=changed,
            interpretation_notes=notes,
        )

    # 9. Itemized sale with inline corrections
    clauses = _split_correction_clauses(normalized)
    qty_history: list[float] = []
    price_history: list[float] = []

    for clause_idx, clause in enumerate(clauses):
        next_is_price_only = False
        if clause_idx + 1 < len(clauses):
            next_nums = extract_numbers_with_positions(clauses[clause_idx + 1])
            if next_nums and _looks_like_price_context(
                clauses[clause_idx + 1], next_nums[0][1], next_nums[0][2]
            ):
                next_is_price_only = True

        sub_clauses = [s.strip() for s in clause.split(",") if s.strip()]
        for sub_idx, sub in enumerate(sub_clauses):
            nums = extract_numbers_with_positions(sub)
            for num_idx, (val, s_pos, end_pos, _tok) in enumerate(nums):
                is_last_in_clause = sub_idx == len(sub_clauses) - 1 and num_idx == len(nums) - 1
                if _looks_like_price_context(sub, s_pos, end_pos) or (
                    is_last_in_clause and next_is_price_only and len(qty_history) >= 1
                ):
                    price_history.append(val)
                else:
                    if (
                        current_draft
                        and current_draft.get("quantity") is not None
                        and current_draft.get("unit_price") is None
                        and not qty_history
                        and clause_idx == 0
                        and len(clauses) == 1
                        and not looks_like_full_new_tx
                    ):
                        price_history.append(val)
                    else:
                        qty_history.append(val)

    changed_fields: list[dict[str, Any]] = []
    notes: list[str] = []

    final_qty: float | None = None
    if qty_history:
        final_qty = qty_history[-1]
        if len(qty_history) > 1:
            changed_fields.append({"field": "quantity", "from": qty_history[0], "to": final_qty})
            notes.append(f"Quantity corrected: {_fmt_num(qty_history[0])} → {_fmt_num(final_qty)}")
        elif current_draft and not looks_like_full_new_tx and current_draft.get("quantity") is not None and current_draft["quantity"] != final_qty:
            changed_fields.append({"field": "quantity", "from": current_draft["quantity"], "to": final_qty})
            notes.append(f"Quantity updated: {_fmt_num(current_draft['quantity'])} → {_fmt_num(final_qty)}")

    final_price: float | None = None
    if price_history:
        final_price = price_history[-1]
        if len(price_history) > 1:
            changed_fields.append({"field": "unit_price", "from": price_history[0], "to": final_price})
            notes.append(f"Unit price corrected: ₹{_fmt_num(price_history[0])} → ₹{_fmt_num(final_price)}")
        elif current_draft and not looks_like_full_new_tx and current_draft.get("unit_price") is not None and current_draft["unit_price"] != final_price:
            changed_fields.append({"field": "unit_price", "from": current_draft["unit_price"], "to": final_price})
            notes.append(f"Unit price updated: ₹{_fmt_num(current_draft['unit_price'])} → ₹{_fmt_num(final_price)}")

    item_name = _extract_item_name(normalized, customer_query, customers)

    return ParseResult(
        intent="upsert",
        entry_type="itemized_sale",
        payment_mode=payment_mode,
        customer_query=customer_query,
        is_explicit_customer_phrase=is_explicit_prefix,
        item_name=item_name,
        quantity=final_qty,
        unit_label=unit_label,
        unit_price=final_price,
        promised_date=promised_date,
        ambiguous_date=ambiguous_date,
        changed_fields=changed_fields,
        interpretation_notes=notes,
    )


def _fmt_num(val: float | int | None) -> str:
    if val is None:
        return ""
    return str(int(val)) if float(val).is_integer() else str(round(float(val), 2))
