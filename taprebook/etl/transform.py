"""ETL transform layer.

This module is the SQL/Python port of the ARRAYFORMULA logic in
docs/artifacts/google_sheets_etl.sql (originally TapRebook_GS_Formulas.txt).

Key transformations:
  * Phone number normalization to E.164 (+91XXXXXXXXXX)
  * Composite appt_id = phone|YYYYMMDD|HHMM
  * Effective status derivation from check-in + check-out updates
  * Procedure-driven recall due dates (Prophy → +180d, New Exam → +365d)
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Phone normalization
# ---------------------------------------------------------------------------

_NON_DIGIT_RE = re.compile(r"[^0-9]")


def normalize_phone(raw: Optional[str], default_country_code: str = "+91") -> Optional[str]:
    """Normalize a phone string to E.164.

    Rules (match the Google Sheets REGEXREPLACE behavior):
      * None / empty → None
      * Starts with '+' → strip spaces, keep as-is
      * Otherwise → strip non-digits, prefix default country code

    >>> normalize_phone("98470 12345")
    '+919847012345'
    >>> normalize_phone("+91 98470 12345")
    '+919847012345'
    >>> normalize_phone("")
    >>> normalize_phone(None)
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.startswith("+"):
        return "+" + _NON_DIGIT_RE.sub("", s)
    return f"{default_country_code}{_NON_DIGIT_RE.sub('', s)}"


# ---------------------------------------------------------------------------
# Composite appointment ID
# ---------------------------------------------------------------------------


def make_appt_id(phone_e164: str, scheduled_at: datetime | pd.Timestamp | str) -> str:
    """Build the composite appt_id used by the Google Sheets prototype.

    Format: '<phone>|YYYYMMDD|HHMM'

    >>> make_appt_id("+919847012345", "2025-09-20 10:00")
    '+919847012345|20250920|1000'
    """
    if isinstance(scheduled_at, str):
        scheduled_at = pd.to_datetime(scheduled_at)
    ts = pd.Timestamp(scheduled_at)
    return f"{phone_e164}|{ts.strftime('%Y%m%d')}|{ts.strftime('%H%M')}"


# ---------------------------------------------------------------------------
# Status derivation (mirrors K2:K "Effective_Status" formula)
# ---------------------------------------------------------------------------


def derive_effective_status(
    appointments: pd.DataFrame,
    updates: pd.DataFrame,
    now: Optional[datetime] = None,
    grace_minutes: int = 15,
) -> pd.DataFrame:
    """Attach 'effective_status' to each appointment.

    Port of the Master!K2 formula. Precedence:
      1. If there is a check-out update for the appt_id, use its status.
      2. Else if now() > scheduled_at + grace_minutes → 'no_show' (overdue).
      3. Else 'scheduled'.

    Parameters
    ----------
    appointments : DataFrame with at least [appt_id, scheduled_at]
    updates      : DataFrame with at least [appt_id, status]
                   status values in {'kept','rebooked','cancelled','no_show'}
    now          : override for testing
    grace_minutes: overdue threshold

    Returns
    -------
    Copy of appointments with 'effective_status' column.
    """
    now = now or datetime.now()
    result = appointments.copy()
    result["scheduled_at"] = pd.to_datetime(result["scheduled_at"])

    # 1. Left-join updates (keep latest if duplicates)
    if not updates.empty:
        latest_updates = (
            updates.sort_values("updated_at" if "updated_at" in updates.columns else "appt_id")
            .drop_duplicates(subset="appt_id", keep="last")
            [["appt_id", "status"]]
            .rename(columns={"status": "update_status"})
        )
        result = result.merge(latest_updates, on="appt_id", how="left")
    else:
        result["update_status"] = None

    # 2. Overdue rule for still-scheduled appts
    overdue_cutoff = now - timedelta(minutes=grace_minutes)
    is_overdue = result["scheduled_at"] < overdue_cutoff

    result["effective_status"] = result["update_status"].fillna(
        pd.Series(["no_show" if o else "scheduled" for o in is_overdue], index=result.index)
    )
    return result.drop(columns=["update_status"])


# ---------------------------------------------------------------------------
# Procedure → recall due dates (port of Master!N2, O2, P2 formulas)
# ---------------------------------------------------------------------------

_PROPHY_RE = re.compile(r"\bProphy\b", re.IGNORECASE)
_NEW_EXAM_RE = re.compile(r"\bNew Exam\b", re.IGNORECASE)


def compute_recall_dates(
    completed_date: Optional[datetime | pd.Timestamp],
    procedures: Optional[str],
    prophy_days: int = 180,
    exam_days: int = 365,
) -> dict[str, Optional[pd.Timestamp]]:
    """Compute cleaning_due, exam_due, and earliest next_due.

    Mirrors the Google Sheets columns N2 (Cleaning_Due), O2 (Exam_Due),
    P2 (Next_Due = earliest non-blank of N & O).
    """
    if completed_date is None or procedures is None:
        return {"cleaning_due": None, "exam_due": None, "next_due": None}

    base = pd.Timestamp(completed_date)
    cleaning_due = base + pd.Timedelta(days=prophy_days) if _PROPHY_RE.search(procedures) else None
    exam_due = base + pd.Timedelta(days=exam_days) if _NEW_EXAM_RE.search(procedures) else None

    candidates = [d for d in (cleaning_due, exam_due) if d is not None]
    next_due = min(candidates) if candidates else None

    return {"cleaning_due": cleaning_due, "exam_due": exam_due, "next_due": next_due}


# ---------------------------------------------------------------------------
# Bulk patient-row transform (what the pipeline calls per batch)
# ---------------------------------------------------------------------------


def transform_checkin_batch(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the standard transforms to a raw check-in CSV DataFrame.

    Expected input columns (from Form_1 schema):
      timestamp, patient_name, mobile, opt_in, appt_date, visit_type, appt_time, arrival_time

    Produces columns suitable for the 'appointments' table load.
    """
    required = {"patient_name", "mobile", "appt_date", "appt_time"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"transform_checkin_batch missing columns: {missing}")

    out = df.copy()
    out["phone_e164"] = out["mobile"].map(normalize_phone)
    out["scheduled_at"] = pd.to_datetime(
        out["appt_date"].astype(str) + " " + out["appt_time"].astype(str),
        errors="coerce",
    )
    # Drop rows with bad data rather than failing silently
    out = out.dropna(subset=["phone_e164", "scheduled_at"])
    out["appt_id"] = [
        make_appt_id(p, t) for p, t in zip(out["phone_e164"], out["scheduled_at"])
    ]
    return out
