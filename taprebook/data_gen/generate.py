"""Generate realistic synthetic data for TapRebook demos.

Design goals
------------
* 3 clinics (matches the 3 pilots in the real Client_Config sheet)
* ~90 days of appointments (enough to show MoM trends and cohort recall)
* Realistic baselines:
    - No-show rate        ≈ 15%   (industry range 10–20%)
    - Review conversion   ≈ 25%
    - Template delivery   ≈ 97%   (healthy BSP number)
* PLANTED EFFECT: the A/B treatment arm (D-1 + T-3h reminders) has a
  ~6 pp higher kept rate than control. This is what the z-test should detect.
* Deterministic — fixed RNG seed so results are stable across runs.

Outputs CSVs to data/sample/:
    clinics.csv, patients.csv, templates.csv, appointments.csv,
    events.csv, template_sends.csv, ab_assignments.csv
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, date
from pathlib import Path

import pandas as pd

from taprebook.config import SAMPLE_DIR, ensure_data_dirs


# ---------------------------------------------------------------------------
# Static reference data
# ---------------------------------------------------------------------------

CLINICS = [
    {
        "clinic_id": "smile_kochi",
        "clinic_name": "Smile Kochi Dental",
        "brand": "Smile Kochi",
        "city": "Kochi",
        "primary_language": "mal",
        "timezone": "Asia/Kolkata",
        "grace_minutes": 15,
        "review_url": "https://g.page/r/smile-kochi",
        "maps_url": "https://maps.google.com/?q=Smile+Kochi+Dental",
        "plan": "Grow",
        "go_live_date": "2025-08-01",
    },
    {
        "clinic_id": "bright_dental",
        "clinic_name": "Bright Dental Care",
        "brand": "Bright Dental",
        "city": "Kochi",
        "primary_language": "en",
        "timezone": "Asia/Kolkata",
        "grace_minutes": 10,
        "review_url": "https://g.page/r/bright-dental",
        "maps_url": "https://maps.google.com/?q=Bright+Dental+Kochi",
        "plan": "Plus",
        "go_live_date": "2025-08-15",
    },
    {
        "clinic_id": "orchid_dental",
        "clinic_name": "Orchid Dental Studio",
        "brand": "Orchid Dental",
        "city": "Kochi",
        "primary_language": "mal",
        "timezone": "Asia/Kolkata",
        "grace_minutes": 15,
        "review_url": "https://g.page/r/orchid-dental",
        "maps_url": "https://maps.google.com/?q=Orchid+Dental",
        "plan": "Lite",
        "go_live_date": "2025-09-01",
    },
]

TEMPLATES = [
    ("CONFIRM_v1",            "Utility",   "en",
     "Appointment confirmed",
     "Hi {{1}}! Your {{2}} is confirmed for {{3}} at {{4}}. Location: {{5}}."),
    ("REM24_v1",              "Utility",   "en",
     "Reminder for tomorrow",
     "Hi {{1}}, reminder for your {{2}} tomorrow at {{3}}."),
    ("REM3H_v1",              "Utility",   "en",
     "See you today",
     "Hi {{1}}, your {{2}} is today at {{3}}. Please arrive 5-10 mins early."),
    ("LATE_v1",               "Utility",   "en",
     "Thanks for the update",
     "We'll hold your slot up to {{1}} mins. What would you like to do?"),
    ("RESCHED_AUTO_v1",       "Utility",   "en",
     "Pick a new time",
     "Choose a new time for {{1}} here:"),
    ("RESCHED_MAN_v1",        "Utility",   "en",
     "Choose a window",
     "For {{1}} on {{2}}, which works best?"),
    ("NOSHOW_REBOOK_v1",      "Utility",   "en",
     "We missed you today",
     "Hi {{1}}, we missed you for {{2}}. Choose a new time."),
    ("RESCHEDULE_CONFIRM_v1", "Utility",   "en",
     "Rescheduled",
     "All set, {{1}}—your {{2}} is now {{3}} at {{4}}."),
    ("REVIEW_v1",             "Marketing", "en",
     "How was your visit?",
     "Hi {{1}}, thanks for visiting {{2}}. Could you leave a quick Google review?"),
    ("REOPEN_v1",             "Utility",   "en",
     "Update about your appointment",
     "We're following up on your {{1}}. Tap below to continue."),
]

SERVICES = [
    ("Consultation",          20),
    ("Prophy (Cleaning)",     45),
    ("New Exam",              30),
    ("Root Canal",            60),
    ("Filling",               30),
    ("Crown Fitting",         45),
    ("Aligner Check",         20),
]

PROVIDERS = ["Dr Menon", "Dr Thomas", "Dr Pillai"]

# A few realistic first/last name lists for Kerala patients (placeholder, synthetic)
FIRST_NAMES = [
    "Anu", "Roy", "Meera", "Jaison", "Priya", "Ajith", "Lakshmi", "Rahul",
    "Sreeja", "Vishnu", "Neha", "Arun", "Kavya", "Manoj", "Divya", "Suresh",
    "Sneha", "Hari", "Reshma", "Vinod", "Anjali", "Nikhil", "Deepa", "Tony",
    "Maria", "George", "Jessy", "Binu", "Rohit", "Smitha",
]
LAST_NAMES = [
    "Mathew", "Cherian", "Nair", "Menon", "Thomas", "Pillai", "George", "Joseph",
    "Kurian", "Antony", "Krishnan", "Rajan", "Unni", "Das", "Raj",
]


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def _rand_phone(rng: random.Random) -> str:
    """Return a plausible Indian mobile number (+91 9XXXXXXXXX)."""
    return "+91" + str(rng.choice([6, 7, 8, 9])) + "".join(str(rng.randint(0, 9)) for _ in range(9))


def _appt_id(phone: str, scheduled_at: datetime) -> str:
    return f"{phone}|{scheduled_at.strftime('%Y%m%d')}|{scheduled_at.strftime('%H%M')}"


def generate(
    n_patients_per_clinic: int = 120,
    days_back: int = 90,
    seed: int = 42,
) -> dict[str, pd.DataFrame]:
    """Generate the full synthetic dataset and write CSVs to data/sample/.

    Returns a dict of DataFrames keyed by table name.
    """
    ensure_data_dirs()
    rng = random.Random(seed)
    today = date.today()

    # -------- clinics ----------
    clinics_df = pd.DataFrame(CLINICS)

    # -------- templates ----------
    templates_rows = []
    for t_id, category, lang, header, body in TEMPLATES:
        templates_rows.append({
            "template_id": t_id, "category": category, "language": lang,
            "header": header, "body": body, "buttons_json": None, "status": "approved",
        })
    templates_df = pd.DataFrame(templates_rows)

    # -------- patients ----------
    patients_rows = []
    for clinic in CLINICS:
        for _ in range(n_patients_per_clinic):
            first = rng.choice(FIRST_NAMES)
            last = rng.choice(LAST_NAMES)
            patients_rows.append({
                "patient_id": f"pat_{uuid.uuid4().hex[:10]}",
                "clinic_id": clinic["clinic_id"],
                "phone_e164": _rand_phone(rng),
                "name": f"{first} {last}",
                "preferred_language": clinic["primary_language"] if rng.random() > 0.3 else "en",
                "opted_in": 1,
                "first_seen_at": None,
                "last_visit_at": None,
                # Cohort tag = month of first visit; fill after appts are generated
                "cohort_tag": None,
            })
    patients_df = pd.DataFrame(patients_rows)

    # -------- appointments + A/B assignments + events + template_sends ----------
    appointments_rows: list[dict] = []
    ab_rows: list[dict] = []
    events_rows: list[dict] = []
    sends_rows: list[dict] = []

    # Baselines — these drive all downstream stats
    BASE_NO_SHOW = 0.15        # 15% no-show if *control* (D-1 only)
    TREATMENT_REDUCTION = 0.06 # treatment arm loses 6pp of no-shows
    CANCEL_RATE = 0.05
    REBOOK_GIVEN_NOSHOW = 0.35 # 35% of no-shows get rebooked via NOSHOW_REBOOK
    REVIEW_REQUEST_RATE = 0.80 # 80% of kept appts → REVIEW_v1 sent
    REVIEW_CONVERSION = 0.25   # 25% of requests → review_left event
    DELIVERY_RATE = 0.97
    READ_RATE = 0.82

    for clinic in CLINICS:
        clinic_patients = patients_df[patients_df.clinic_id == clinic["clinic_id"]].to_dict("records")
        clinic_go_live = datetime.strptime(clinic["go_live_date"], "%Y-%m-%d").date()

        # Each patient gets 1–3 appointments in the window
        for patient in clinic_patients:
            n_appts = rng.choices([1, 2, 3], weights=[0.55, 0.30, 0.15])[0]
            for _ in range(n_appts):
                # Distribute appointments across the 90-day window
                days_offset = rng.randint(0, days_back - 1)
                appt_date = today - timedelta(days=days_offset)
                # Clinics only have data after go-live
                if appt_date < clinic_go_live:
                    continue
                hour = rng.choice([9, 10, 11, 12, 14, 15, 16, 17])
                minute = rng.choice([0, 30])
                scheduled_at = datetime.combine(appt_date, datetime.min.time()).replace(
                    hour=hour, minute=minute
                )
                service_name, duration = rng.choice(SERVICES)
                provider = rng.choice(PROVIDERS)

                appt_id = _appt_id(patient["phone_e164"], scheduled_at)

                # --- A/B assignment (only for reminder-eligible appts, i.e. future+D-1) ---
                variant = rng.choice(["control", "treatment"])
                ab_rows.append({
                    "experiment_key": "reminder_cadence_v1",
                    "patient_id": patient["patient_id"],
                    "appt_id": appt_id,
                    "variant": variant,
                    "assigned_at": (scheduled_at - timedelta(days=2)).isoformat(),
                })

                # --- Status (past appts get terminal status; future ones stay scheduled) ---
                if scheduled_at >= datetime.now():
                    status = "scheduled"
                else:
                    r = rng.random()
                    effective_noshow = BASE_NO_SHOW
                    if variant == "treatment":
                        effective_noshow = max(0.03, BASE_NO_SHOW - TREATMENT_REDUCTION)

                    if r < CANCEL_RATE:
                        status = "cancelled"
                    elif r < CANCEL_RATE + effective_noshow:
                        # Of these no-shows, some get rebooked via NOSHOW_REBOOK flow
                        status = "rebooked" if rng.random() < REBOOK_GIVEN_NOSHOW else "no_show"
                    else:
                        status = "kept"

                appointments_rows.append({
                    "appt_id": appt_id,
                    "clinic_id": clinic["clinic_id"],
                    "patient_id": patient["patient_id"],
                    "provider": provider,
                    "service": service_name,
                    "scheduled_at": scheduled_at.isoformat(),
                    "duration_minutes": duration,
                    "status": status,
                    "booking_source": rng.choices(["automated", "manual"], [0.7, 0.3])[0],
                    "created_at": (scheduled_at - timedelta(days=rng.randint(1, 30))).isoformat(),
                    "updated_at": scheduled_at.isoformat(),
                })

                # --- Template sends + events for this appt ---
                # 1. CONFIRM_v1 at booking
                confirm_sent_at = scheduled_at - timedelta(days=rng.randint(1, 14))
                _emit_send(sends_rows, clinic, patient, appt_id, "CONFIRM_v1",
                           confirm_sent_at, rng, DELIVERY_RATE, READ_RATE)
                events_rows.append(_event(confirm_sent_at, clinic, patient, appt_id,
                                          "confirm", service_name))

                # 2. REM24_v1 always sent (both arms)
                rem24_sent_at = scheduled_at - timedelta(days=1)
                if rem24_sent_at < datetime.now():
                    _emit_send(sends_rows, clinic, patient, appt_id, "REM24_v1",
                               rem24_sent_at, rng, DELIVERY_RATE, READ_RATE)
                    events_rows.append(_event(rem24_sent_at, clinic, patient, appt_id,
                                              "remind_d1", service_name))

                # 3. REM3H_v1 only for treatment
                if variant == "treatment":
                    rem3h_sent_at = scheduled_at - timedelta(hours=3)
                    if rem3h_sent_at < datetime.now():
                        _emit_send(sends_rows, clinic, patient, appt_id, "REM3H_v1",
                                   rem3h_sent_at, rng, DELIVERY_RATE, READ_RATE)
                        events_rows.append(_event(rem3h_sent_at, clinic, patient, appt_id,
                                                  "remind_t3h", service_name))

                # 4. Post-visit flows (only if terminal)
                if status == "kept":
                    # Review request ~2–4h after appt
                    if rng.random() < REVIEW_REQUEST_RATE:
                        review_sent_at = scheduled_at + timedelta(hours=rng.choice([2, 3, 4]))
                        _emit_send(sends_rows, clinic, patient, appt_id, "REVIEW_v1",
                                   review_sent_at, rng, DELIVERY_RATE, READ_RATE)
                        events_rows.append(_event(review_sent_at, clinic, patient, appt_id,
                                                  "review_sent", service_name))
                        if rng.random() < REVIEW_CONVERSION:
                            left_at = review_sent_at + timedelta(hours=rng.randint(1, 48))
                            events_rows.append(_event(left_at, clinic, patient, appt_id,
                                                      "review_left", service_name,
                                                      outcome="review_left"))
                elif status in ("no_show", "rebooked"):
                    # NOSHOW_REBOOK sent shortly after the missed slot
                    rebook_sent_at = scheduled_at + timedelta(hours=2)
                    _emit_send(sends_rows, clinic, patient, appt_id, "NOSHOW_REBOOK_v1",
                               rebook_sent_at, rng, DELIVERY_RATE, READ_RATE)
                    events_rows.append(_event(rebook_sent_at, clinic, patient, appt_id,
                                              "noshow", service_name,
                                              outcome="rebooked" if status == "rebooked" else "noshow"))

    appointments_df = pd.DataFrame(appointments_rows)
    ab_df = pd.DataFrame(ab_rows)
    events_df = pd.DataFrame(events_rows)
    sends_df = pd.DataFrame(sends_rows)

    # Fill cohort_tag = first-kept-visit month
    first_keep = (
        appointments_df[appointments_df.status == "kept"]
        .sort_values("scheduled_at")
        .groupby("patient_id")["scheduled_at"].first()
        .reset_index()
    )
    first_keep["cohort_tag"] = pd.to_datetime(first_keep["scheduled_at"]).dt.strftime("pilot_%Y%m")
    patients_df = patients_df.merge(
        first_keep[["patient_id", "cohort_tag"]].rename(columns={"cohort_tag": "_tag"}),
        on="patient_id", how="left",
    )
    patients_df["cohort_tag"] = patients_df["_tag"].fillna(patients_df["cohort_tag"])
    patients_df = patients_df.drop(columns=["_tag"])

    # Write all CSVs
    out = {
        "clinics":        clinics_df,
        "patients":       patients_df,
        "templates":      templates_df,
        "appointments":   appointments_df,
        "events":         events_df,
        "template_sends": sends_df,
        "ab_assignments": ab_df,
    }
    for name, df in out.items():
        df.to_csv(SAMPLE_DIR / f"{name}.csv", index=False)

    return out


def _emit_send(rows: list[dict], clinic, patient, appt_id: str, template_id: str,
               sent_at: datetime, rng: random.Random,
               delivery_rate: float, read_rate: float) -> None:
    """Helper: append one template_sends row with realistic funnel flags."""
    delivered = rng.random() < delivery_rate
    read = delivered and rng.random() < read_rate
    replied = read and rng.random() < 0.18
    rows.append({
        "sent_at": sent_at.isoformat(),
        "clinic_id": clinic["clinic_id"],
        "patient_id": patient["patient_id"],
        "appt_id": appt_id,
        "template_id": template_id,
        "delivered": int(delivered),
        "read": int(read),
        "clicked": int(read and rng.random() < 0.25),
        "replied": int(replied),
        "reply_intent": None,
        "reply_language": None,
    })


def _event(ts: datetime, clinic, patient, appt_id: str, event_type: str,
           service: str, outcome: str | None = None) -> dict:
    return {
        "event_ts": ts.isoformat(),
        "clinic_id": clinic["clinic_id"],
        "patient_id": patient["patient_id"],
        "appt_id": appt_id,
        "event_type": event_type,
        "service": service,
        "outcome": outcome,
        "value": None,
        "wa_sent": 1,
        "wa_delivered": 1,
        "wa_read": 1 if outcome in (None, "review_left", "rebooked") else 0,
        "notes": None,
    }


def main() -> None:
    print("Generating synthetic data...")
    out = generate()
    for name, df in out.items():
        print(f"  {name:20s} {len(df):>6d} rows → {(SAMPLE_DIR / (name + '.csv')).relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
