"""
Tolemate booking, driven by code instead of by the model's good behaviour.

Why this exists (real chats, 2026-10-05): a customer gave the service, city,
date, name and email — and the 3B model never once called the booking tool. It
kept asking for details already given, and sometimes announced a confirmed
booking that did not exist. Prompting harder doesn't fix a model that skips
steps, so the steps are now code:

  1. the model only READS the conversation (structured JSON extraction);
  2. code works out what is still missing and asks for exactly that;
  3. code searches providers, checks availability, and creates the booking by
     calling the real tools itself;
  4. code writes the reply from the tool results — so it can never claim a
     booking, an availability or a price that no tool returned.

Anything the customer types that is not a booking (cancellations, general
questions) is declined here and handled by the agent's normal loop.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.agents.flow import ConversationFlow, FlowOutcome, RunTool
from app.core.logging import get_logger
from app.services.ai.base import AIProvider, AIProviderError, ChatMessage

logger = get_logger(__name__)

SEARCH_TOOL = "search_service_providers"
AVAILABILITY_TOOL = "check_provider_availability"
BOOKING_TOOL = "create_service_booking"
BOOKING_PROOF = "Booking confirmed:"
CONFIRM_MARKER = "Reply YES to confirm"
FLOW_CALL_PREFIX = "flow-"

EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["book", "cancel", "other"]},
        "service": {"type": "string"},
        "location": {"type": "string"},
        "provider": {"type": "string"},
        "date_text": {"type": "string"},
        "name": {"type": "string"},
    },
    "required": ["intent", "service", "location", "provider", "date_text", "name"],
}

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_STRONG_CONFIRM = re.compile(r"\b(confirm\w*|proceed|go ahead|book it|do it|make the booking)\b", re.I)
_WEAK_CONFIRM = re.compile(r"\b(yes|yeah|yep|yup|ok|okay|sure|correct|right)\b", re.I)
_NEGATIVE = re.compile(r"\b(no|not|don'?t|do not|stop|wait|change|instead|actually)\b", re.I)
_ANY_LOCATION = re.compile(r"\b(any\w*|every\w*|all|whatever|system|exist\w*|near\s*me)\b", re.I)

_FILLER_WORDS = {"the", "one", "please", "want", "like", "with", "for", "and", "that", "this", "need", "take", "pick", "choose", "go"}
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
_DAY_ABBR = {d: d[:3].capitalize() for d in _WEEKDAYS}


# --------------------------------------------------------------------- dates


def resolve_date_text(text: str, today: date) -> date | None:
    """Turn what the customer typed ("tomorrow", "Friday", "12 October",
    "2026-10-09", "9/10") into a date. Done in code because a language model
    has no clock and is unreliable at weekday arithmetic."""
    t = text.strip().lower()
    if not t:
        return None

    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    if "day after tomorrow" in t:
        return today + timedelta(days=2)
    if "tomorrow" in t:
        return today + timedelta(days=1)
    if re.search(r"\btoday\b|\btonight\b", t):
        return today

    for index, weekday in enumerate(_WEEKDAYS):
        if re.search(rf"\b{weekday}\b|\b{weekday[:3]}\b", t):
            ahead = (index - today.weekday()) % 7
            if ahead == 0 and "next" in t:
                ahead = 7
            return today + timedelta(days=ahead)

    month_names = "|".join(_MONTHS + [m[:3] for m in _MONTHS])
    day_first = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({month_names})\b", t)
    month_first = re.search(rf"\b({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", t)
    numeric = re.search(r"\b(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?\b", t)

    day = month = year = None
    if day_first:
        day, month = int(day_first.group(1)), _month_number(day_first.group(2))
    elif month_first:
        month, day = _month_number(month_first.group(1)), int(month_first.group(2))
    elif numeric:
        day, month = int(numeric.group(1)), int(numeric.group(2))  # day-first, as locally written
        if numeric.group(3):
            year = int(numeric.group(3))
            year += 2000 if year < 100 else 0
    if day is None or month is None:
        return None

    year = year or today.year
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None
    if candidate < today and not (numeric and numeric.group(3)):
        try:
            candidate = date(year + 1, month, day)
        except ValueError:
            return None
    return candidate


def _month_number(name: str) -> int:
    name = name.lower()
    for i, month in enumerate(_MONTHS, start=1):
        if month == name or month[:3] == name:
            return i
    raise ValueError(name)


def display_date(d: date) -> str:
    return f"{d:%A} {d.day} {d:%B %Y}"


# ---------------------------------------------------------------- candidates


@dataclass
class Candidate:
    id: str
    label: str
    location: str = ""
    price: str = ""
    open_text: str = ""

    @property
    def hours(self) -> str:
        return summarise_hours(self.open_text)


def summarise_hours(open_text: str) -> str:
    """"Monday 09:00-17:00, Tuesday 09:00-17:00, ..." -> "Mon-Fri 09:00-17:00"."""
    items = re.findall(r"([A-Za-z]+)\s+(\d{1,2}:\d{2})-(\d{1,2}:\d{2})", open_text)
    if not items:
        return open_text.strip()
    hours = {(start, end) for _, start, end in items}
    days = [d.lower() for d, _, _ in items]
    if len(hours) == 1:
        start, end = next(iter(hours))
        indexes = sorted(_WEEKDAYS.index(d) for d in days if d in _WEEKDAYS)
        if indexes and indexes == list(range(indexes[0], indexes[-1] + 1)) and len(indexes) > 2:
            span = f"{_DAY_ABBR[_WEEKDAYS[indexes[0]]]}-{_DAY_ABBR[_WEEKDAYS[indexes[-1]]]}"
        else:
            span = ", ".join(_DAY_ABBR.get(d, d.title()) for d in days)
        return f"{span} {start}-{end}"
    return open_text.strip()


_CANDIDATE_RE = re.compile(
    r"(?P<label>[^;()]+?)\s*\((?P<location>[^,()]+),\s*rating\s+[\d.]+(?:,\s*(?P<price>[\d.]+))?,"
    r"\s*id=(?P<id>[\w-]+)\)(?P<tail>[^;]*)"
)


def parse_candidates(tool_text: str) -> list[Candidate]:
    """Recover offered providers from a stored search_service_providers result."""
    if tool_text.startswith("[TOOL RESULT"):
        tool_text = tool_text.split("\n", 1)[-1]
    found = []
    for m in _CANDIDATE_RE.finditer(tool_text):
        tail = m.group("tail") or ""
        open_text = tail.split("open:", 1)[1].strip() if "open:" in tail else ""
        found.append(
            Candidate(
                id=m.group("id"),
                label=m.group("label").strip(),
                location=m.group("location").strip(),
                price=m.group("price") or "",
                open_text=open_text,
            )
        )
    return found


def candidate_from_data(p: dict[str, Any]) -> Candidate:
    label = p.get("name", "")
    if p.get("vendor_name"):
        label = f"{label} by {p['vendor_name']}"
    open_text = ", ".join(p.get("open_days") or p.get("available_dates") or [])
    price = "" if p.get("price") is None else str(p["price"])
    return Candidate(id=str(p["id"]), label=label, location=p.get("location", ""), price=price, open_text=open_text)


def match_provider(choice: str, candidates: list[Candidate]) -> Candidate | None:
    choice = choice.strip().lower()
    if not choice:
        return None
    ordinal = re.fullmatch(r"(?:no\.?\s*|number\s*|#)?(\d{1,2})(?:st|nd|rd|th)?", choice)
    if ordinal and 1 <= int(ordinal.group(1)) <= len(candidates):
        return candidates[int(ordinal.group(1)) - 1]
    for word, index in (("first", 0), ("second", 1), ("third", 2)):
        if choice == word and index < len(candidates):
            return candidates[index]
    for c in candidates:
        if choice == c.id.lower():
            return c
    contained = [c for c in candidates if choice in c.label.lower() or c.label.lower() in choice]
    if len(contained) == 1:
        return contained[0]
    if len(contained) > 1:
        return None  # e.g. just "cleaning" fits several providers: not a choice yet
    words = {w for w in re.findall(r"[a-z]+", choice) if len(w) > 2 and w not in _FILLER_WORDS}
    if not words:
        return None
    scored = sorted(
        (
            (len(words & set(re.findall(r"[a-z]+", c.label.lower()))) / len(words), c)
            for c in candidates
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    best_score, best = scored[0]
    # Two providers matching equally well means the customer hasn't actually
    # chosen one (e.g. just "cleaning") — ask, don't guess.
    if best_score < 0.6 or (len(scored) > 1 and scored[1][0] == best_score):
        return None
    return best


def _same_service(a: str, b: str) -> bool:
    wa = {w for w in re.findall(r"[a-z]+", a.lower()) if len(w) > 3}
    wb = {w for w in re.findall(r"[a-z]+", b.lower()) if len(w) > 3}
    return a.strip().lower() == b.strip().lower() or bool(wa & wb)


# ----------------------------------------------------------------- the flow


class BookingFlow(ConversationFlow):
    async def handle(
        self,
        *,
        user_message: str,
        history: list[ChatMessage],
        ai_provider: AIProvider,
        run_tool: RunTool,
    ) -> FlowOutcome | None:
        today = _today()
        segment = _segment_after_last_booking(history)
        user_texts = [m.content for m in segment if m.role == "user"] + [user_message]
        last_search_service, candidates = _last_search(segment)
        in_progress = any((m.tool_call_id or "").startswith(FLOW_CALL_PREFIX) for m in segment)

        try:
            extracted = await ai_provider.extract_json(
                _extraction_messages(segment, user_message, candidates, today), EXTRACTION_SCHEMA
            )
        except AIProviderError as exc:
            logger.warning("booking_flow_extraction_failed", error=str(exc))
            return None

        intent = str(extracted.get("intent", "other"))
        if intent == "cancel" or (intent != "book" and not in_progress):
            return None

        service = _clean(extracted.get("service"))
        location = _clean(extracted.get("location"))
        if _ANY_LOCATION.search(location):
            location = ""
        provider_text = _clean(extracted.get("provider"))
        date_text = _clean(extracted.get("date_text"))
        name = _validated_name(_clean(extracted.get("name")), user_texts)
        email = _last_email(user_texts)

        # ---- provider -----------------------------------------------------
        provider_hit = match_provider(provider_text, candidates)
        needs_search = not candidates or (
            service and last_search_service and not _same_service(service, last_search_service) and not provider_hit
        )
        if needs_search:
            if not service:
                return FlowOutcome(
                    "What service do you need? For example plumbing, cleaning or electrical work.",
                    step="ask_service",
                )
            args: dict[str, Any] = {"service": service}
            if location:
                args["location"] = location
            result = await run_tool(SEARCH_TOOL, args)
            if result.is_error:
                return FlowOutcome(f"I couldn't search just now: {result.content}", step="search_error")
            providers = (result.data or {}).get("providers") or []
            if not providers:
                where = f" in {location}" if location else ""
                return FlowOutcome(
                    f"I couldn't find any {service} providers{where}. Would you like to try another "
                    "service or area?",
                    step="no_providers",
                )
            candidates = [candidate_from_data(p) for p in providers]
            provider_hit = match_provider(provider_text, candidates)

        chosen = provider_hit or (candidates[0] if len(candidates) == 1 else None)
        if chosen is None:
            lines = [f"{i}. {c.label}" + _price_and_hours(c) for i, c in enumerate(candidates, start=1)]
            return FlowOutcome(
                "I found these:\n" + "\n".join(lines) + "\nWhich one would you like?",
                step="choose_provider",
            )

        # ---- date ---------------------------------------------------------
        hours = f" It's open {chosen.hours}." if chosen.hours else ""
        if not date_text:
            return FlowOutcome(
                f"Which day would you like {chosen.label}?{hours}", step="ask_date"
            )
        wanted = resolve_date_text(date_text, today)
        if wanted is None:
            return FlowOutcome(
                "I didn't catch the date. Please say a day like “Friday”, “tomorrow” or “12 October”.",
                step="bad_date",
            )
        if wanted < today:
            return FlowOutcome(
                f"That date has already passed — today is {display_date(today)}. Which upcoming day "
                "would you like?",
                step="past_date",
            )

        # ---- availability (a real check, never assumed) ---------------------
        check = await run_tool(AVAILABILITY_TOOL, {"provider_id": chosen.id, "date": wanted.isoformat()})
        if check.is_error:
            return FlowOutcome(f"I couldn't check that day: {check.content}", step="availability_error")
        if (check.data or {}).get("available") is False:
            return FlowOutcome(
                f"{chosen.label} isn't available on {display_date(wanted)}.{hours} Which other day suits you?",
                step="unavailable",
            )

        # ---- customer details --------------------------------------------
        missing = [w for w, have in (("your name", name), ("your email address", email)) if not have]
        if missing:
            return FlowOutcome(
                f"{chosen.label} is available on {display_date(wanted)}. To book it I just need "
                + " and ".join(missing) + ".",
                step="ask_details",
            )

        # ---- confirmation ------------------------------------------------
        summary = (
            f"{chosen.label}{_price(chosen)} on {display_date(wanted)} (ToleMate books the 10:00 slot), "
            f"for {name} <{email}>."
        )
        last_assistant = next((m.content for m in reversed(segment) if m.role == "assistant" and m.content), "")
        shown_same = summary in last_assistant
        shown_other = CONFIRM_MARKER in last_assistant and not shown_same
        negative = bool(_NEGATIVE.search(user_message))
        strong = bool(_STRONG_CONFIRM.search(user_message)) and not negative
        weak = bool(_WEAK_CONFIRM.search(user_message)) and not negative and len(user_message.split()) <= 6
        if not ((shown_same and (strong or weak)) or (strong and not shown_other)):
            return FlowOutcome(f"Please check: {summary} {CONFIRM_MARKER} and I'll book it.", step="confirm")

        # ---- the booking, for real --------------------------------------------
        booked = await run_tool(
            BOOKING_TOOL,
            {
                "provider_id": chosen.id,
                "date": wanted.isoformat(),
                "customer_name": name,
                "customer_email": email,
            },
        )
        if booked.is_error:
            return FlowOutcome(_booking_error_reply(booked.content, email), step="booking_error")
        data = booked.data or {}
        reference = data.get("booking_id", "")
        return FlowOutcome(
            f"Booked! Reference {reference}: {chosen.label} on {display_date(wanted)} "
            f"(10:00 slot), status {data.get('status', 'pending')}. I created a ToleMate account for "
            f"{email} — use “Forgot password” on the ToleMate site to log in and see this booking.",
            step="booked",
            extras={"booking": data},
        )


# ------------------------------------------------------------------ helpers


def _today() -> date:
    # A function so tests can pin "today".
    return date.today()


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"none", "null", "n/a", "unknown", "not given", "not provided"} else text


def _price(c: Candidate) -> str:
    return f", Rs {c.price}" if c.price else ""


def _price_and_hours(c: Candidate) -> str:
    bits = [f"Rs {c.price}" if c.price else "", c.hours]
    return " — " + " — ".join(b for b in bits if b) if any(bits) else ""


def _last_email(user_texts: list[str]) -> str:
    """Taken straight from what the customer typed, never from the model:
    a small model repeated one back as `...com.auau`."""
    for text in reversed(user_texts):
        found = _EMAIL.findall(text)
        if found:
            return found[-1]
    return ""


def _validated_name(name: str, user_texts: list[str]) -> str:
    """Only accept a name the customer actually wrote — the model otherwise
    fills in placeholders like "Customer Name"."""
    if not name or len(name) > 60:
        return ""
    joined = " ".join(user_texts).lower()
    return name if re.search(rf"\b{re.escape(name.lower())}\b", joined) else ""


def _segment_after_last_booking(history: list[ChatMessage]) -> list[ChatMessage]:
    """Messages since the last completed booking, so a second booking in the
    same chat doesn't inherit the first one's date, name or provider."""
    last = -1
    for i, m in enumerate(history):
        if m.role == "tool" and BOOKING_PROOF in m.content:
            last = i
    return history[last + 1 :]


def _last_search(segment: list[ChatMessage]) -> tuple[str, list[Candidate]]:
    calls: dict[str, tuple[str, dict]] = {}
    service, candidates = "", []
    for m in segment:
        for tc in m.tool_calls:
            calls[tc.id] = (tc.name, tc.arguments or {})
        if m.role == "tool" and m.tool_call_id in calls and calls[m.tool_call_id][0] == SEARCH_TOOL:
            parsed = parse_candidates(m.content)
            if parsed:
                service, candidates = str(calls[m.tool_call_id][1].get("service", "")), parsed
    return service, candidates


def _extraction_messages(
    segment: list[ChatMessage], user_message: str, candidates: list[Candidate], today: date
) -> list[ChatMessage]:
    turns = [
        f"{'Customer' if m.role == 'user' else 'Assistant'}: {m.content}"
        for m in segment
        if m.role in ("user", "assistant") and m.content
    ][-8:]
    turns.append(f"Customer: {user_message}")
    offered = "\n".join(f"{i}. {c.label} (id {c.id})" for i, c in enumerate(candidates, start=1)) or "none yet"
    system = (
        "You read a conversation between a customer and a service-booking assistant and "
        "report what the CUSTOMER has said, as JSON. Use an empty string for anything the "
        "customer has not said. Never guess.\n"
        "intent: 'book' if they want to book a service (including answering the assistant's "
        "booking questions), 'cancel' if they want to cancel a booking, else 'other'.\n"
        "service: the kind of service they want (e.g. plumbing, office cleaning).\n"
        "location: the city or area they named.\n"
        "provider: which of the offered providers they chose (its name), if any.\n"
        "date_text: the day they asked for, copied exactly as they wrote it (e.g. 'tomorrow', "
        "'Friday', '12 October').\n"
        "name: the customer's own name, if they gave it."
    )
    user = (
        f"Today is {today:%A %Y-%m-%d}.\nProviders already offered:\n{offered}\n\n"
        "Conversation:\n" + "\n".join(turns)
    )
    return [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]


def _booking_error_reply(message: str, email: str) -> str:
    if "already has a ToleMate account" in message:
        return (
            f"{email} already has a ToleMate account, so I can't create a booking under it from here. "
            "Please use a different email, or book on the ToleMate website while logged in."
        )
    return f"I couldn't complete the booking: {message}"
