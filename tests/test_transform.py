"""Unit tests for taprebook.etl.transform.

Ports and verifies the Google Sheets formula logic:
  * Phone → E.164 normalization (GS: REGEXREPLACE + "+91" prefix rule)
  * Composite appt_id (GS: phone | YYYYMMDD | HHMM)
  * Effective status derivation (GS: Master!K2 formula)
  * Recall due dates (GS: Master!N2, O2, P2)
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from taprebook.etl.transform import (
    compute_recall_dates,
    derive_effective_status,
    make_appt_id,
    normalize_phone,
    transform_checkin_batch,
)


# ---------------------------------------------------------------------------
# normalize_phone
# ---------------------------------------------------------------------------


class TestNormalizePhone:

    def test_plain_10_digit_gets_plus_91(self):
        assert normalize_phone("9847012345") == "+919847012345"

    def test_with_spaces(self):
        assert normalize_phone("98470 12345") == "+919847012345"

    def test_with_hyphens(self):
        assert normalize_phone("98470-12345") == "+919847012345"

    def test_already_has_plus(self):
        assert normalize_phone("+91 98470 12345") == "+919847012345"

    def test_preserves_non_india_country_code(self):
        assert normalize_phone("+1 415 555 0123") == "+14155550123"

    def test_empty_returns_none(self):
        assert normalize_phone("") is None

    def test_whitespace_returns_none(self):
        assert normalize_phone("   ") is None

    def test_none_returns_none(self):
        assert normalize_phone(None) is None

    def test_numeric_input(self):
        # pandas often delivers phone as int/float
        assert normalize_phone(9847012345) == "+919847012345"


# ---------------------------------------------------------------------------
# make_appt_id
# ---------------------------------------------------------------------------


class TestMakeApptId:

    def test_from_string(self):
        assert make_appt_id("+919847012345", "2025-09-20 10:00") == "+919847012345|20250920|1000"

    def test_from_datetime(self):
        dt = datetime(2025, 9, 20, 10, 30)
        assert make_appt_id("+919847012345", dt) == "+919847012345|20250920|1030"

    def test_zero_padding_hour(self):
        assert make_appt_id("+911", "2025-01-05 09:00") == "+911|20250105|0900"

    def test_unique_per_slot_same_patient(self):
        phone = "+919000000001"
        a = make_appt_id(phone, "2025-09-20 10:00")
        b = make_appt_id(phone, "2025-09-20 10:30")
        assert a != b


# ---------------------------------------------------------------------------
# derive_effective_status
# ---------------------------------------------------------------------------


class TestDeriveEffectiveStatus:

    def _appts(self, n: int = 3) -> pd.DataFrame:
        base = datetime(2025, 9, 20, 10, 0)
        return pd.DataFrame([
            {"appt_id": f"a{i}", "scheduled_at": base + timedelta(hours=i)}
            for i in range(n)
        ])

    def test_no_updates_future_appts_are_scheduled(self):
        # All appts in the future → 'scheduled'
        appts = self._appts(2)
        appts["scheduled_at"] = datetime.now() + timedelta(days=1)
        out = derive_effective_status(appts, pd.DataFrame(columns=["appt_id", "status"]))
        assert set(out["effective_status"]) == {"scheduled"}

    def test_past_appt_without_update_becomes_no_show(self):
        appts = pd.DataFrame([{
            "appt_id": "a1",
            "scheduled_at": datetime.now() - timedelta(hours=2),
        }])
        out = derive_effective_status(
            appts, pd.DataFrame(columns=["appt_id", "status"]), grace_minutes=15,
        )
        assert out.loc[0, "effective_status"] == "no_show"

    def test_update_overrides_overdue(self):
        # Past appt, but check-out marked it 'kept'
        appts = pd.DataFrame([{
            "appt_id": "a1",
            "scheduled_at": datetime.now() - timedelta(hours=2),
        }])
        updates = pd.DataFrame([{"appt_id": "a1", "status": "kept"}])
        out = derive_effective_status(appts, updates, grace_minutes=15)
        assert out.loc[0, "effective_status"] == "kept"

    def test_latest_update_wins(self):
        # Two updates for same appt; most recent should apply
        appts = pd.DataFrame([{
            "appt_id": "a1",
            "scheduled_at": datetime.now() - timedelta(days=1),
        }])
        updates = pd.DataFrame([
            {"appt_id": "a1", "status": "no_show",  "updated_at": "2025-09-20 10:00"},
            {"appt_id": "a1", "status": "rebooked", "updated_at": "2025-09-20 14:00"},
        ])
        out = derive_effective_status(appts, updates)
        assert out.loc[0, "effective_status"] == "rebooked"

    def test_grace_period_respected(self):
        # Scheduled 5 min ago, grace=15 → still scheduled (not yet overdue)
        appts = pd.DataFrame([{
            "appt_id": "a1",
            "scheduled_at": datetime.now() - timedelta(minutes=5),
        }])
        out = derive_effective_status(
            appts, pd.DataFrame(columns=["appt_id", "status"]), grace_minutes=15,
        )
        assert out.loc[0, "effective_status"] == "scheduled"


# ---------------------------------------------------------------------------
# compute_recall_dates
# ---------------------------------------------------------------------------


class TestComputeRecallDates:

    def test_prophy_triggers_180d_cleaning_due(self):
        r = compute_recall_dates(datetime(2025, 9, 20), "Prophy (Cleaning)")
        assert r["cleaning_due"] == pd.Timestamp("2026-03-19")
        assert r["exam_due"] is None
        assert r["next_due"] == pd.Timestamp("2026-03-19")

    def test_new_exam_triggers_365d_exam_due(self):
        r = compute_recall_dates(datetime(2025, 9, 20), "New Exam")
        assert r["exam_due"] == pd.Timestamp("2026-09-20")
        assert r["cleaning_due"] is None
        assert r["next_due"] == pd.Timestamp("2026-09-20")

    def test_both_procedures_picks_earliest(self):
        # Prophy (180d) fires before New Exam (365d), so cleaning wins
        r = compute_recall_dates(datetime(2025, 9, 20), "Prophy (Cleaning), New Exam")
        assert r["next_due"] == r["cleaning_due"]

    def test_no_match_returns_none(self):
        r = compute_recall_dates(datetime(2025, 9, 20), "Filling")
        assert r["cleaning_due"] is None
        assert r["exam_due"] is None
        assert r["next_due"] is None

    def test_none_inputs(self):
        r = compute_recall_dates(None, "Prophy (Cleaning)")
        assert r["next_due"] is None


# ---------------------------------------------------------------------------
# transform_checkin_batch (integration)
# ---------------------------------------------------------------------------


class TestTransformCheckinBatch:

    def test_happy_path(self):
        df = pd.DataFrame([{
            "timestamp": "2025-09-20 08:00",
            "patient_name": "Anu Mathew",
            "mobile": "9847012345",
            "opt_in": "Yes",
            "appt_date": "2025-09-20",
            "visit_type": "Consultation",
            "appt_time": "10:00",
            "arrival_time": "",
        }])
        out = transform_checkin_batch(df)
        assert out.loc[0, "phone_e164"] == "+919847012345"
        assert out.loc[0, "appt_id"] == "+919847012345|20250920|1000"

    def test_drops_bad_rows(self):
        df = pd.DataFrame([
            {"patient_name": "A", "mobile": "9847012345",
             "appt_date": "2025-09-20", "appt_time": "10:00"},
            {"patient_name": "B", "mobile": "",            # bad phone
             "appt_date": "2025-09-20", "appt_time": "10:00"},
            {"patient_name": "C", "mobile": "9847099999",
             "appt_date": "not-a-date", "appt_time": "xx"},  # bad datetime
        ])
        out = transform_checkin_batch(df)
        assert len(out) == 1
        assert out.iloc[0]["patient_name"] == "A"

    def test_missing_required_column_raises(self):
        df = pd.DataFrame([{"mobile": "9847012345"}])
        with pytest.raises(ValueError, match="missing columns"):
            transform_checkin_batch(df)
