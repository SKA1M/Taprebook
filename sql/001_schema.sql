-- =====================================================================
-- TapRebook — Core schema (SQLite dialect; ANSI-compatible where possible)
-- =====================================================================
-- This schema is the SQL port of the Google Sheets prototype
-- (see docs/artifacts/google_sheets_etl.sql for the original ARRAYFORMULA/QUERY logic).
--
-- Design notes:
--   * Surrogate IDs for facts (events, template_sends) so we can replay
--     the same webhook payload idempotently at the app layer.
--   * appt_id is a composite natural key (phone|YYYYMMDD|HHMM) carried over
--     from the Google Sheets prototype. Kept as TEXT for portability.
--   * All timestamps stored in UTC-naive TEXT (ISO-8601). Conversion to
--     clinic-local time happens in views/queries using `strftime`.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Dimension: clinics
-- One row per clinic/branch. Drives per-clinic config (grace mins, links).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clinics (
    clinic_id          TEXT PRIMARY KEY,
    clinic_name        TEXT NOT NULL,
    brand              TEXT,
    city               TEXT DEFAULT 'Kochi',
    primary_language   TEXT NOT NULL CHECK (primary_language IN ('en','mal')),
    timezone           TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    grace_minutes      INTEGER NOT NULL DEFAULT 15,
    review_url         TEXT,
    maps_url           TEXT,
    plan               TEXT CHECK (plan IN ('Lite','Grow','Plus','Multi')),
    go_live_date       DATE,
    created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- Dimension: patients
-- Phone is the natural key inside a clinic; (clinic_id, phone_e164) is unique.
-- cohort_tag lets us group patients for recall / pilot analysis.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patients (
    patient_id         TEXT PRIMARY KEY,
    clinic_id          TEXT NOT NULL REFERENCES clinics(clinic_id),
    phone_e164         TEXT NOT NULL,
    name               TEXT,
    preferred_language TEXT CHECK (preferred_language IN ('en','mal')),
    opted_in           INTEGER NOT NULL DEFAULT 1,  -- SQLite boolean
    first_seen_at      TEXT,
    last_visit_at      TEXT,
    cohort_tag         TEXT,
    UNIQUE (clinic_id, phone_e164)
);

-- ---------------------------------------------------------------------
-- Dimension: WhatsApp message templates (Interakt-managed)
-- Mirrors the templates under templates/*.csv. Category drives compliance
-- (Utility vs Marketing) per Meta rules.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS templates (
    template_id    TEXT PRIMARY KEY,                       -- e.g. CONFIRM_v1
    category       TEXT NOT NULL CHECK (category IN ('Utility','Marketing')),
    language       TEXT NOT NULL CHECK (language IN ('en','mal')),
    header         TEXT,
    body           TEXT NOT NULL,
    buttons_json   TEXT,                                   -- JSON array of button specs
    status         TEXT NOT NULL DEFAULT 'approved'
                       CHECK (status IN ('approved','pending','rejected','paused')),
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- Fact: appointments
-- Statuses follow the Google Sheets "Effective_Status" computation:
--   scheduled → kept | no_show | rebooked | cancelled
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS appointments (
    appt_id            TEXT PRIMARY KEY,                   -- phone|YYYYMMDD|HHMM
    clinic_id          TEXT NOT NULL REFERENCES clinics(clinic_id),
    patient_id         TEXT NOT NULL REFERENCES patients(patient_id),
    provider           TEXT,
    service            TEXT,
    scheduled_at       TEXT NOT NULL,                      -- ISO-8601
    duration_minutes   INTEGER NOT NULL DEFAULT 30,
    status             TEXT NOT NULL DEFAULT 'scheduled'
                           CHECK (status IN ('scheduled','kept','no_show','rebooked','cancelled')),
    booking_source     TEXT CHECK (booking_source IN ('automated','manual','walk_in')),
    created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- Fact: events (matches the 10-col schema from TapRebook_KPI_Tracker)
-- Append-only event log. Any change of state emits a row here; this is
-- what feeds analytics and what you'd replay to rebuild state.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    event_ts       TEXT NOT NULL,
    clinic_id      TEXT NOT NULL REFERENCES clinics(clinic_id),
    patient_id     TEXT REFERENCES patients(patient_id),
    appt_id        TEXT REFERENCES appointments(appt_id),
    event_type     TEXT NOT NULL,                          -- confirm | remind_d1 | remind_t3h | late | reschedule | noshow | review_sent | review_left | checkin
    service        TEXT,
    outcome        TEXT,                                   -- kept | rebooked | noshow | review_left | ...
    value          REAL,
    wa_sent        INTEGER,                                -- boolean
    wa_delivered   INTEGER,
    wa_read        INTEGER,
    notes          TEXT
);

-- ---------------------------------------------------------------------
-- Fact: template_sends
-- One row per outbound WhatsApp template send. This is what feeds
-- delivery/read funnels and template health reports.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS template_sends (
    send_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at         TEXT NOT NULL,
    clinic_id       TEXT NOT NULL REFERENCES clinics(clinic_id),
    patient_id      TEXT NOT NULL REFERENCES patients(patient_id),
    appt_id         TEXT REFERENCES appointments(appt_id),
    template_id     TEXT NOT NULL REFERENCES templates(template_id),
    delivered       INTEGER NOT NULL DEFAULT 0,
    read            INTEGER NOT NULL DEFAULT 0,
    clicked         INTEGER NOT NULL DEFAULT 0,
    replied         INTEGER NOT NULL DEFAULT 0,
    reply_intent    TEXT,                                  -- populated by triage module
    reply_language  TEXT
);

-- ---------------------------------------------------------------------
-- Experiment: A/B assignments
-- Used by taprebook.experiments.ab_reminder_cadence
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ab_assignments (
    assignment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_key  TEXT NOT NULL,                         -- e.g. reminder_cadence_v1
    patient_id      TEXT NOT NULL REFERENCES patients(patient_id),
    appt_id         TEXT NOT NULL REFERENCES appointments(appt_id),
    variant         TEXT NOT NULL CHECK (variant IN ('control','treatment')),
    assigned_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (experiment_key, appt_id)
);
