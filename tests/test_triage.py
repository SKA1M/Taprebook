"""Unit tests for taprebook.triage.classifier.

The LLM path requires ANTHROPIC_API_KEY; those tests are skipped when it's
missing. The rule-based fallback is fully testable in CI.
"""
from __future__ import annotations

import os

import pytest

from taprebook.triage.classifier import (
    _TEMPLATE_SUGGESTIONS,
    triage,
    triage_rule_based,
)


# ---------------------------------------------------------------------------
# Rule-based classifier
# ---------------------------------------------------------------------------


class TestRuleBased:

    @pytest.mark.parametrize("text", [
        "yes",
        "confirmed",
        "OK, see you then",
        "sure, I'll be there",
    ])
    def test_english_confirm(self, text):
        r = triage_rule_based(text)
        assert r.intent == "confirm"
        assert r.language == "en"
        assert not r.used_llm

    @pytest.mark.parametrize("text", [
        "cancel please",
        "Sorry, can't make it",
        "not coming today",
    ])
    def test_english_cancel(self, text):
        assert triage_rule_based(text).intent == "cancel"

    def test_running_late(self):
        r = triage_rule_based("running late, stuck in traffic")
        assert r.intent == "running_late"
        assert r.suggested_reply_template == "LATE_v1"

    def test_reschedule_auto(self):
        r = triage_rule_based("Can I reschedule to a different day?")
        assert r.intent == "reschedule_auto"
        assert r.suggested_reply_template == "RESCHED_AUTO_v1"

    def test_reschedule_window(self):
        r = triage_rule_based("morning works better for me")
        assert r.intent == "reschedule_window"
        assert r.suggested_reply_template == "RESCHED_MAN_v1"

    def test_malayalam_confirm_unicode(self):
        r = triage_rule_based("ശരി, വരാം")
        assert r.intent == "confirm"
        assert r.language == "mal"

    def test_manglish_confirm(self):
        r = triage_rule_based("sheri, varam")
        assert r.intent == "confirm"
        assert r.language == "mal"

    def test_manglish_running_late(self):
        r = triage_rule_based("vaikum")
        assert r.intent == "running_late"
        assert r.language == "mal"

    def test_malayalam_cancel(self):
        r = triage_rule_based("cancel ചെയ്യണം")
        assert r.intent == "cancel"

    def test_question_is_catchall(self):
        r = triage_rule_based("will it hurt?")
        assert r.intent == "question"

    def test_empty_input(self):
        r = triage_rule_based("")
        assert r.intent == "other"
        assert r.confidence == 0.0

    def test_gibberish_falls_to_other(self):
        r = triage_rule_based("xyzzy foobar")
        assert r.intent == "other"

    def test_every_intent_has_template_mapping(self):
        """Regression: keep _TEMPLATE_SUGGESTIONS in sync with Intent literal."""
        expected_intents = {
            "confirm", "cancel", "reschedule_auto", "reschedule_window",
            "running_late", "no_show_rebook", "review_intent", "question", "other",
        }
        assert set(_TEMPLATE_SUGGESTIONS.keys()) == expected_intents


# ---------------------------------------------------------------------------
# Public triage() dispatcher
# ---------------------------------------------------------------------------


class TestTriageDispatcher:

    def test_without_api_key_falls_back_to_rules(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        # Also patch the imported constant, since config reads env at import time
        monkeypatch.setattr("taprebook.triage.classifier.ANTHROPIC_API_KEY", "")
        r = triage("yes, confirmed")
        assert r.intent == "confirm"
        assert r.used_llm is False


# ---------------------------------------------------------------------------
# LLM path (skipped without API key)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping live LLM test",
)
class TestLLMIntegration:

    def test_llm_classifies_confirm(self):
        from taprebook.triage.classifier import triage_llm
        r = triage_llm("yes that works, I'll be there tomorrow at 10")
        assert r is not None
        assert r.intent == "confirm"
        assert r.used_llm is True

    def test_llm_classifies_malayalam(self):
        from taprebook.triage.classifier import triage_llm
        r = triage_llm("ശരി, നാളെ 10 മണിക്ക് വരാം")
        assert r is not None
        assert r.intent == "confirm"
        assert r.language in ("mal", "mixed")
