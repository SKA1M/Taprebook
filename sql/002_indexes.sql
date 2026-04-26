-- =====================================================================
-- Indexes — chosen from actual query patterns in sql/queries/*.sql
-- =====================================================================
-- Principles:
--   * Index the (clinic_id, time) prefix because nearly every KPI filters
--     by clinic and groups by month/day.
--   * Index status and event_type for filter-heavy aggregations.
--   * Index phone_e164 for the inbound-webhook lookup (Interakt → patient).
-- =====================================================================

-- Appointments: "no-show rate by clinic by month" and "reminders due"
CREATE INDEX IF NOT EXISTS idx_appointments_clinic_scheduled
    ON appointments (clinic_id, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_appointments_status
    ON appointments (status);
CREATE INDEX IF NOT EXISTS idx_appointments_patient
    ON appointments (patient_id, scheduled_at);

-- Events: funnel queries and per-clinic time-series
CREATE INDEX IF NOT EXISTS idx_events_clinic_ts
    ON events (clinic_id, event_ts);
CREATE INDEX IF NOT EXISTS idx_events_type_ts
    ON events (event_type, event_ts);
CREATE INDEX IF NOT EXISTS idx_events_appt
    ON events (appt_id);

-- Template sends: template-health dashboard + reminder funnel
CREATE INDEX IF NOT EXISTS idx_template_sends_template_sent
    ON template_sends (template_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_template_sends_appt
    ON template_sends (appt_id);
CREATE INDEX IF NOT EXISTS idx_template_sends_patient_sent
    ON template_sends (patient_id, sent_at);

-- Patients: inbound webhook resolves phone → patient
CREATE INDEX IF NOT EXISTS idx_patients_phone
    ON patients (phone_e164);
CREATE INDEX IF NOT EXISTS idx_patients_cohort
    ON patients (cohort_tag);

-- A/B: join path for experiment analysis
CREATE INDEX IF NOT EXISTS idx_ab_experiment_variant
    ON ab_assignments (experiment_key, variant);
