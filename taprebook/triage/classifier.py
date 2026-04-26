"""LLM-powered intent triage for inbound WhatsApp replies.

Primary path uses the Anthropic API (Claude Haiku by default — fast + cheap
for short classifications). Falls back to a rule-based regex matcher when the
SDK isn't installed or no API key is set, so the repo runs in any environment.

Supported intents (matched to the template suite in templates/):
    * confirm            — patient confirms the appointment as-is
    * cancel             — explicit cancel request
    * reschedule_auto    — wants to use the booking link
    * reschedule_window  — asks for morning/afternoon/evening
    * running_late       — tells us they'll be late
    * no_show_rebook     — accepts one of the rebook slot offers
    * review_intent      — indicates they've left / will leave a review
    * question           — an open question needing human handoff
    * other              — catch-all (triage to /handoff)

Languages supported:
    * English
    * Malayalam (including transliterated "Manglish")
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal, Optional

from taprebook.config import ANTHROPIC_API_KEY, TRIAGE_MODEL


Intent = Literal[
    "confirm",
    "cancel",
    "reschedule_auto",
    "reschedule_window",
    "running_late",
    "no_show_rebook",
    "review_intent",
    "question",
    "other",
]

Language = Literal["en", "mal", "mixed", "unknown"]


@dataclass
class TriageResult:
    intent: Intent
    language: Language
    confidence: float              # 0.0–1.0
    suggested_reply_template: Optional[str]  # e.g. "RESCHED_AUTO_v1"
    reasoning: str
    used_llm: bool


# ---------------------------------------------------------------------------
# Rule-based fallback (also used as a ground-truth baseline in tests)
# ---------------------------------------------------------------------------

_RULES: list[tuple[re.Pattern[str], Intent, Language]] = [
    # English
    (re.compile(r"\b(yes|y|confirm(ed)?|ok|okay|sure|fine|going to come)\b", re.I),
     "confirm", "en"),
    (re.compile(r"\b(cancel|no longer|wont come|not coming|can'?t make it)\b", re.I),
     "cancel", "en"),
    (re.compile(r"\b(running late|stuck in traffic|will be late|late by|delayed)\b", re.I),
     "running_late", "en"),
    (re.compile(r"\b(reschedule|change (the )?time|different (time|day)|new slot)\b", re.I),
     "reschedule_auto", "en"),
    (re.compile(r"\b(morning|afternoon|evening)\b", re.I),
     "reschedule_window", "en"),
    (re.compile(r"\b(review|left a review|google review|5 stars?)\b", re.I),
     "review_intent", "en"),
    (re.compile(r"\b(book a|book another|rebook|see more times|option a|option b)\b", re.I),
     "no_show_rebook", "en"),
    (re.compile(r"\?", re.I),
     "question", "en"),

    # Malayalam (Unicode) — very small starter set
    (re.compile(r"(ശരി|സമ്മതം|വരാം|ok ആണ്)"), "confirm", "mal"),
    (re.compile(r"(വരുന്നില്ല|ക്യാൻസൽ|റദ്ദാക്കുക|cancel)"), "cancel", "mal"),
    (re.compile(r"(വൈകും|late ആകും|late ആയി|താമസിക്കും)"), "running_late", "mal"),
    (re.compile(r"(reschedule|മാറ്റണം|സമയം മാറ്റാമോ)"), "reschedule_auto", "mal"),

    # Manglish (transliterated)
    (re.compile(r"\b(sheri|sherry|varam|varunnu|vanno)\b", re.I), "confirm", "mal"),
    (re.compile(r"\b(varilla|varunnilla|illa)\b", re.I),   "cancel", "mal"),
    (re.compile(r"\b(vaikum|late aakum|late aayi|thamasikum)\b", re.I), "running_late", "mal"),
]


_TEMPLATE_SUGGESTIONS: dict[Intent, Optional[str]] = {
    "confirm":           None,                      # acknowledge, no template needed
    "cancel":            None,                      # human handoff
    "reschedule_auto":   "RESCHED_AUTO_v1",
    "reschedule_window": "RESCHED_MAN_v1",
    "running_late":      "LATE_v1",
    "no_show_rebook":    "RESCHEDULE_CONFIRM_v1",
    "review_intent":     None,
    "question":          None,                      # /handoff
    "other":             None,
}


def _detect_language_fallback(text: str) -> Language:
    """Quick language detect: Malayalam unicode block + common Manglish markers."""
    if re.search(r"[\u0D00-\u0D7F]", text):
        return "mal"
    if re.search(r"\b(sheri|varunnu|vaikum|illa|varam)\b", text, re.I):
        return "mal"
    return "en"


def triage_rule_based(text: str) -> TriageResult:
    """Rule-based classifier — always available, no network calls."""
    if not text or not text.strip():
        return TriageResult(
            intent="other", language="unknown", confidence=0.0,
            suggested_reply_template=None,
            reasoning="empty input", used_llm=False,
        )

    for pattern, intent, language in _RULES:
        if pattern.search(text):
            return TriageResult(
                intent=intent,
                language=language,
                confidence=0.7,   # rules are decent but not great
                suggested_reply_template=_TEMPLATE_SUGGESTIONS[intent],
                reasoning=f"matched rule /{pattern.pattern}/",
                used_llm=False,
            )

    # No rule matched: fall back to language detection only
    return TriageResult(
        intent="other",
        language=_detect_language_fallback(text),
        confidence=0.3,
        suggested_reply_template=None,
        reasoning="no rule matched",
        used_llm=False,
    )


# ---------------------------------------------------------------------------
# LLM-based classifier
# ---------------------------------------------------------------------------

_LLM_SYSTEM_PROMPT = """You are a triage classifier for a dental clinic's WhatsApp inbox \
in Kochi, Kerala. Patients reply in English, Malayalam, or transliterated Manglish.

Classify each patient message into exactly one of these intents:
- confirm:            patient confirms they will attend as scheduled
- cancel:             explicit cancel request
- reschedule_auto:    wants a new time via booking link
- reschedule_window:  asks for morning/afternoon/evening
- running_late:       will arrive late to today's appointment
- no_show_rebook:     accepts a rebook slot after a missed appointment
- review_intent:      indicates they left or will leave a Google review
- question:           an open question requiring human handoff
- other:              catch-all

Also detect language: en | mal | mixed | unknown.

Respond in strict JSON with keys: intent, language, confidence (0.0–1.0), reasoning (one short sentence).
No markdown, no prose outside the JSON.
"""


def triage_llm(
    text: str,
    api_key: Optional[str] = None,
    model: str = TRIAGE_MODEL,
) -> Optional[TriageResult]:
    """Classify via the Anthropic API. Returns None if SDK unavailable or key missing."""
    key = api_key or ANTHROPIC_API_KEY
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    client = anthropic.Anthropic(api_key=key)
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=200,
            system=_LLM_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
    except Exception as e:
        # Network / auth / rate limit — caller falls back to rules
        return TriageResult(
            intent="other", language="unknown", confidence=0.0,
            suggested_reply_template=None,
            reasoning=f"llm error: {type(e).__name__}",
            used_llm=False,
        )

    raw = msg.content[0].text if msg.content else "{}"
    # Defensive JSON extraction (some models wrap in ```json ... ```)
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None

    intent = parsed.get("intent", "other")
    if intent not in _TEMPLATE_SUGGESTIONS:
        intent = "other"

    return TriageResult(
        intent=intent,                                       # type: ignore[arg-type]
        language=parsed.get("language", "unknown"),          # type: ignore[arg-type]
        confidence=float(parsed.get("confidence", 0.8)),
        suggested_reply_template=_TEMPLATE_SUGGESTIONS[intent],  # type: ignore[index]
        reasoning=parsed.get("reasoning", ""),
        used_llm=True,
    )


# ---------------------------------------------------------------------------
# Public entrypoint: try LLM, fall back to rules
# ---------------------------------------------------------------------------


def triage(text: str, prefer_llm: bool = True) -> TriageResult:
    """Classify an inbound reply. LLM-first with rule-based fallback."""
    if prefer_llm:
        llm_result = triage_llm(text)
        if llm_result is not None and llm_result.used_llm:
            return llm_result
    return triage_rule_based(text)
