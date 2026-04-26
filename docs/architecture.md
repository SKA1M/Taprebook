# Architecture

## System at a glance

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Clinic intake   │    │  Patient replies │    │  Interakt BSP    │
│  (Google Form)   │    │  (WhatsApp)      │    │  (WhatsApp API)  │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         │                       │                       │
         │ CSV export            │ webhook               │ delivery receipts
         ▼                       ▼                       ▼
┌────────────────────────────────────────────────────────────────┐
│                   taprebook.etl (Python)                       │
│                                                                │
│   extract  →  transform  →  load                               │
│               (phone E.164,                                    │
│                composite PK,                                   │
│                status rules)                                   │
└────────────────────────┬───────────────────────────────────────┘
                         │
                         ▼
                 ┌──────────────────┐
                 │   SQLite         │
                 │                  │
                 │  7 tables        │
                 │  5 views         │
                 │  9 indexes       │
                 └──────────┬───────┘
                            │
      ┌─────────────────────┼─────────────────────┐
      ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────────┐
│  KPI queries │    │  A/B test    │    │   Streamlit      │
│  (6 files)   │    │  (z-test)    │    │   dashboard      │
└──────────────┘    └──────────────┘    └──────────────────┘
```

## Why SQLite

Picking SQLite was a deliberate choice:

- **Runs anywhere.** `make init-db` works on a laptop with no services to start. Anyone reviewing this repo gets the full thing working in under a minute.
- **Boring and sufficient.** For ~1k appointments/clinic/month, even naive queries finish in milliseconds.
- **Portable.** The schema is ANSI-compatible enough that migrating to Postgres is a one-day job (swap `AUTOINCREMENT` for `SERIAL`, `strftime` for `to_char`, `REGEXMATCH` is already Python-side).

## Data model

### Dimensions

| Table | Grain | Keyed by |
|---|---|---|
| `clinics` | One row per clinic/branch | `clinic_id` |
| `patients` | One row per patient per clinic | `patient_id` (unique on `clinic_id + phone_e164`) |
| `templates` | One row per approved WhatsApp template | `template_id` (e.g. `CONFIRM_v1`) |

### Facts

| Table | Grain | Write pattern |
|---|---|---|
| `appointments` | One row per scheduled slot | Upsert on `appt_id` (state mutates) |
| `events` | One row per state change | Append-only |
| `template_sends` | One row per outbound template send | Append-only |
| `ab_assignments` | One row per randomized unit | Append-only, unique on `(experiment_key, appt_id)` |

### The composite key

`appt_id = phone_e164 | YYYYMMDD | HHMM`

This is carried over from the Google Sheets prototype where it served as a natural join key across check-in and check-out forms. It survives in the SQL port because it makes every webhook idempotent — the same appointment gets the same ID whether it's rebuilt from the check-in form or constructed from a reschedule webhook.

## ETL flow

1. **Extract** (`taprebook/etl/extract.py`) — read CSVs (today) or hit the Google Sheets API / Interakt webhook stream (production).
2. **Transform** (`taprebook/etl/transform.py`) — the hard part. Direct Python port of the `ARRAYFORMULA`s in `docs/artifacts/google_sheets_etl.sql`:
   - `normalize_phone()` — strip non-digits, default to `+91` prefix
   - `make_appt_id()` — composite key
   - `derive_effective_status()` — precedence: explicit update > overdue rule > scheduled
   - `compute_recall_dates()` — Prophy → +180d, New Exam → +365d
3. **Load** (`taprebook/etl/load.py`) — `INSERT OR REPLACE` for dimensions and appointments (idempotent), plain `INSERT` for append-only facts.

## Analytical views

The views in `sql/003_views.sql` are the semantic layer — queries and the dashboard read from them, not raw tables. This is where metric definitions live:

- `v_monthly_no_show_rate` — drops `status = 'scheduled'` from the denominator (only terminal appts count)
- `v_reminder_funnel` — de-duplicates to one row per reminder-eligible appt
- `v_template_health` — funnel percentages conditioned on the previous stage
- `v_patient_cohorts` — first *kept* appointment defines the cohort
- `v_cohort_recall` — classic retention triangle with month-offset math
- `v_ab_reminder_cadence` — pre-joins A/B assignments to terminal status for the stat test

If I ever redefine "no-show rate," I change it once here, not in six dashboards.

## LLM triage

`taprebook/triage/classifier.py` is a hybrid: Anthropic Claude Haiku is the primary classifier; a deterministic rule-based matcher is the fallback. The split matters because:

- The LLM handles ambiguity ("I think I might be a little late today")
- The rules cover the 80% of cases that are literally "yes" or "cancel"
- The repo runs in CI with no API key (rules only); production gets the LLM path for free

Both paths return the same `TriageResult` dataclass, so downstream code (auto-reply, handoff) doesn't know or care which fired.

## What's explicitly not built

Worth saying out loud so this doc doesn't oversell:

- **No auth/multi-tenancy.** Single-DB prototype.
- **No real-time orchestrator.** The reminder scheduler exists only conceptually — the generator simulates what it would emit.
- **No Postgres migration.** SQLite is load-bearing. The schema is ANSI-ish but no one has exercised it on Postgres yet.
- **No production BSP.** The Interakt client has a live mode but it's never been tested against real credentials in this repo.
