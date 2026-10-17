"""One chat turn: free text (typed or voice transcript) -> updated UI profile + what was heard.

The Buyer Intelligence agent extracts a profile patch (Gemini when configured, the offline
template extractor otherwise); :mod:`app.journey.intent` folds it into the profile screen's
fields. The assistant keeps asking, one question at a time, until budget, bedrooms, property
type and town have all been answered (what counts as answered is remembered per session).
"""

from __future__ import annotations

import re
from threading import Lock

from app.agents.buyer_intelligence import BuyerIntelligenceAgent
from app.journey.intent import Heard, apply_patch
from app.journey.profile import buyer_to_ui
from app.repositories.session_repository import SessionRepository
from app.schemas.common import AgentTraceOut
from app.schemas.journey import UIProfile

ORDER = ["budget", "bedrooms", "type", "town"]
QUESTIONS = {
    "budget": ("What's the most you'd like to spend?", "What is the most you would like to spend?"),
    "bedrooms": ("How many bedrooms do you need?", "How many bedrooms do you need?"),
    "type": ("HDB, condo or both?", "Are you thinking HDB, condo, or both?"),
    "town": ("Which area do you have in mind?", "Which area do you have in mind?"),
}
BUDGET_CHOICES = ["Under $600k", "Under $900k", "Under $1.2M", "No limit"]
BED_CHOICES = ["2 bedrooms", "3 bedrooms", "4 bedrooms", "5+ bedrooms"]
TYPE_CHOICES = {"HDB only": ["HDB"], "Condo only": ["Condo"], "Both": ["HDB", "Condo"]}
QUICK_REPLIES = TYPE_CHOICES  # kept for callers that import it
DONE = "Perfect. Check it, then I’ll rank."
DONE_SPOKEN = "Perfect. Check your profile, then I will rank."

_BUDGET = re.compile(r"\$?\s*(\d+(?:[.,]\d+)?)\s*(k|m|mil|million|thousand)?\b", re.I)
_state: dict[str, dict] = {}  # session_id -> {"answered": set[str], "pending": str | None}
_lock = Lock()


def parse_budget(text: str) -> float | None:
    """'under $900k', '1.2M', '800,000' -> SGD. A bare small number is not a budget."""
    for m in _BUDGET.finditer(text.replace(",", "")):
        n, unit = float(m.group(1)), (m.group(2) or "").lower()
        n *= {"k": 1e3, "thousand": 1e3, "m": 1e6, "mil": 1e6, "million": 1e6}.get(unit, 1)
        if n >= 100_000:
            return n
    return None


def parse_bedrooms(text: str) -> int | None:
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "studio": 1}
    m = re.search(r"\b(\d)\b", text) or re.search(r"\b(one|two|three|four|five|studio)\b", text, re.I)
    if not m:
        return None
    val = int(m.group(1)) if m.group(1).isdigit() else words[m.group(1).lower()]
    return val if 0 < val <= 9 else None


class ChatService:
    def __init__(
        self, agent: BuyerIntelligenceAgent, session_repo: SessionRepository, ui_towns: list[str],
        popular_towns: list[str] | None = None,
    ) -> None:
        self._popular = popular_towns or ui_towns
        self._agent = agent
        self._sessions = session_repo
        self._ui_towns = ui_towns

    def _answer_pending(self, key: str, message: str, profile: UIProfile) -> tuple[UIProfile, str] | None:
        """Deterministically read a short reply to the question we just asked ("3", "900k", "Bishan")."""
        text = message.strip()
        low = text.lower()
        if key == "budget":
            if re.search(r"no (limit|cap)|any|unlimited|flexible", low):
                return profile.model_copy(update={"budget": 5_000_000.0}), "no budget cap"
            b = parse_budget(text)
            if b:
                return profile.model_copy(update={"budget": b}), f"≤ ${round(b / 1000):,}k"
        elif key == "bedrooms":
            n = parse_bedrooms(text)
            if n is not None:
                return profile.model_copy(update={"min_bed": n}), f"{n}+ bedrooms"
        elif key == "type":
            if re.search(r"\bboth\b|either|any", low):
                return profile.model_copy(update={"types": ["HDB", "Condo"]}), "HDB + Condo"
            has_h, has_c = "hdb" in low, bool(re.search(r"condo|\bec\b|apartment", low))
            if has_h or has_c:
                types = [t for t, on in (("HDB", has_h), ("Condo", has_c)) if on]
                return profile.model_copy(update={"types": types}), " + ".join(types)
        elif key == "town":
            if re.search(r"anywhere|any (town|area)|no preference|don'?t mind", low):
                return profile.model_copy(update={"towns": list(self._ui_towns)}), "any town"
            found = [t for t in self._ui_towns if t.lower() in low]
            if found:
                return profile.model_copy(update={"towns": found}), " · ".join(found)
        return None

    def turn(
        self, request_id: str, session_id: str, message: str, client_profile: UIProfile | None,
        restart: bool = False,
    ) -> dict:
        self._sessions.get_or_create(session_id)
        profile = client_profile or buyer_to_ui(self._sessions.get_profile(session_id))
        with _lock:
            st = _state.setdefault(session_id, {"answered": set(), "pending": None})
            if restart:
                st["answered"], st["pending"] = set(), None
            pending = st["pending"]
            if pending is None and message.strip() in TYPE_CHOICES:
                pending = "type"

        heard, warnings, trace, used_llm = Heard(), [], [], False
        direct = self._answer_pending(pending, message, profile) if pending and len(message) <= 60 else None
        if direct is not None:  # a plain answer to the question just asked needs no model call
            profile, label = direct
            heard.must.append(label)
            heard.got.add(pending)
        else:
            result = self._agent.run(request_id, message, {})
            data = result.data or {}
            profile, heard, warnings = apply_patch(profile, data.get("profile_patch", {}), message, self._ui_towns)
            warnings = [*result.warnings, *warnings]
            t = AgentTraceOut.from_agent_result(result)
            t.detail = f"{len(heard.must) + len(heard.nice)} fields"
            trace, used_llm = [t.model_dump()], bool(data.get("used_llm"))

        with _lock:
            st["answered"] |= heard.got
            missing = [k for k in ORDER if k not in st["answered"]]
            st["pending"] = missing[0] if missing else None
            nxt = st["pending"]
        if nxt:
            heard.ask.append(QUESTIONS[nxt][0])
        return self._reply(session_id, profile, heard, warnings, trace, used_llm, nxt)

    def _reply(
        self, session_id: str, profile: UIProfile, heard: Heard, warnings: list[str],
        trace: list[dict], used_llm: bool, nxt: str | None = None,
    ) -> dict:
        quick = {"budget": BUDGET_CHOICES, "bedrooms": BED_CHOICES, "type": list(TYPE_CHOICES),
                 "town": [*self._popular, "Anywhere"]}.get(nxt or "", [])
        return {
            "session_id": session_id,
            "stage": "ask" if nxt else "done",
            "asking": nxt,
            "reply": QUESTIONS[nxt][0] if nxt else DONE,
            "speak": QUESTIONS[nxt][1] if nxt else DONE_SPOKEN,
            "quick_replies": quick,
            "profile": profile.model_dump(),
            "heard": {"must": heard.must, "nice": heard.nice, "ask": heard.ask, "unknown": heard.unknown},
            "chips": heard.chips(),
            "used_llm": used_llm,
            "warnings": warnings,
            "trace": trace,
        }
