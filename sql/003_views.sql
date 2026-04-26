-- =====================================================================
-- Analytical views — the "semantic layer" for dashboards and reports.
--
-- These wrap the raw facts so that the Streamlit dashboard and the
-- scripts/run_all_kpis.py reporter can issue simple SELECTs instead
-- of re-deriving metric definitions every time. Every view here is
-- referenced by at least one query file in sql/queries/ or by the
-- dashboard.
-- =====================================================================

-- ---------------------------------------------------------------------
-- v_monthly_no_show_rate
-- Excludes appointments still open (status='scheduled') so the denominator
-- is only appointments that have reached a terminal state.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_monthly_no_show_rate;
CREATE VIEW v_monthly_no_show_rate AS
SELECT
    clinic_id,
    strftime('%Y-%m', scheduled_at)                                              AS month,
    COUNT(*)                                                                     AS terminal_appts,
    SUM(CASE WHEN status = 'kept'      THEN 1 ELSE 0 END)                        AS kept,
    SUM(CASE WHEN status = 'rebooked'  THEN 1 ELSE 0 END)                        AS rebooked,
    SUM(CASE WHEN status = 'no_show'   THEN 1 ELSE 0 END)                        AS no_shows,
    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END)                        AS cancelled,
    ROUND(
        100.0 * SUM(CASE WHEN status = 'no_show' THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0), 2
    )                                                                            AS no_show_rate_pct
FROM appointments
WHERE status IN ('kept','rebooked','no_show','cancelled')
GROUP BY clinic_id, month;


-- ---------------------------------------------------------------------
-- v_reminder_funnel
-- Tracks the reminder-to-kept funnel at the appointment level.
-- One row per reminder-eligible appointment; conditional counts at each step.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_reminder_funnel;
CREATE VIEW v_reminder_funnel AS
WITH reminder_sends AS (
    SELECT
        ts.appt_id,
        ts.clinic_id,
        MIN(ts.sent_at)                              AS first_reminder_sent_at,
        MAX(ts.delivered)                            AS delivered,
        MAX(ts.read)                                 AS read_ind,
        MAX(ts.replied)                              AS replied
    FROM template_sends ts
    JOIN templates t ON t.template_id = ts.template_id
    WHERE t.template_id IN ('REM24_v1','REM3H_v1')
    GROUP BY ts.appt_id, ts.clinic_id
)
SELECT
    r.clinic_id,
    strftime('%Y-%m', r.first_reminder_sent_at)                                  AS month,
    COUNT(*)                                                                     AS reminders_sent,
    SUM(r.delivered)                                                             AS delivered,
    SUM(r.read_ind)                                                              AS read_count,
    SUM(r.replied)                                                               AS replied,
    SUM(CASE WHEN a.status = 'kept'     THEN 1 ELSE 0 END)                       AS kept,
    SUM(CASE WHEN a.status = 'rebooked' THEN 1 ELSE 0 END)                       AS rebooked,
    SUM(CASE WHEN a.status = 'no_show'  THEN 1 ELSE 0 END)                       AS no_show
FROM reminder_sends r
JOIN appointments a ON a.appt_id = r.appt_id
GROUP BY r.clinic_id, month;


-- ---------------------------------------------------------------------
-- v_template_health
-- Per-template delivery & read rates; used to spot template degradation.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_template_health;
CREATE VIEW v_template_health AS
SELECT
    ts.template_id,
    t.category,
    t.language,
    COUNT(*)                                                                     AS sent,
    SUM(ts.delivered)                                                            AS delivered,
    SUM(ts.read)                                                                 AS read_count,
    SUM(ts.replied)                                                              AS replied,
    ROUND(100.0 * SUM(ts.delivered) / NULLIF(COUNT(*), 0),      2)               AS delivery_rate_pct,
    ROUND(100.0 * SUM(ts.read)      / NULLIF(SUM(ts.delivered), 0), 2)           AS read_rate_pct,
    ROUND(100.0 * SUM(ts.replied)   / NULLIF(SUM(ts.read),      0), 2)           AS reply_rate_pct
FROM template_sends ts
JOIN templates t ON t.template_id = ts.template_id
GROUP BY ts.template_id, t.category, t.language;


-- ---------------------------------------------------------------------
-- v_patient_cohorts
-- Assigns each patient to a cohort = month of first kept visit.
-- Used by v_cohort_recall and the recall dashboard.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_patient_cohorts;
CREATE VIEW v_patient_cohorts AS
SELECT
    p.patient_id,
    p.clinic_id,
    MIN(strftime('%Y-%m', a.scheduled_at)) AS cohort_month,
    MIN(a.scheduled_at)                    AS cohort_start_at
FROM patients p
JOIN appointments a ON a.patient_id = p.patient_id
WHERE a.status = 'kept'
GROUP BY p.patient_id, p.clinic_id;


-- ---------------------------------------------------------------------
-- v_cohort_recall
-- Classic cohort retention grid: rows=cohort_month, cols=months_since.
-- Value = count of distinct patients from that cohort who kept an appt
-- in that offset month. month_offset=0 is the cohort size itself.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_cohort_recall;
CREATE VIEW v_cohort_recall AS
WITH visits AS (
    SELECT
        pc.clinic_id,
        pc.patient_id,
        pc.cohort_month,
        strftime('%Y-%m', a.scheduled_at) AS visit_month,
        -- SQLite date math: months between two 'YYYY-MM' strings
        (CAST(strftime('%Y', a.scheduled_at) AS INTEGER) * 12
         + CAST(strftime('%m', a.scheduled_at) AS INTEGER))
        -
        (CAST(substr(pc.cohort_month, 1, 4) AS INTEGER) * 12
         + CAST(substr(pc.cohort_month, 6, 2) AS INTEGER))
                                          AS month_offset
    FROM v_patient_cohorts pc
    JOIN appointments a
        ON a.patient_id = pc.patient_id
       AND a.status     = 'kept'
)
SELECT
    clinic_id,
    cohort_month,
    month_offset,
    COUNT(DISTINCT patient_id)            AS active_patients
FROM visits
WHERE month_offset BETWEEN 0 AND 12
GROUP BY clinic_id, cohort_month, month_offset;


-- ---------------------------------------------------------------------
-- v_ab_reminder_cadence
-- Join A/B assignments to terminal appointment status for the
-- reminder_cadence_v1 experiment. Python then runs the statistical test.
-- ---------------------------------------------------------------------
DROP VIEW IF EXISTS v_ab_reminder_cadence;
CREATE VIEW v_ab_reminder_cadence AS
SELECT
    ab.variant,
    COUNT(*)                                                 AS n,
    SUM(CASE WHEN a.status = 'kept'    THEN 1 ELSE 0 END)    AS kept,
    SUM(CASE WHEN a.status = 'no_show' THEN 1 ELSE 0 END)    AS no_shows,
    ROUND(100.0 * SUM(CASE WHEN a.status = 'kept' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 2)                    AS kept_rate_pct
FROM ab_assignments ab
JOIN appointments a ON a.appt_id = ab.appt_id
WHERE ab.experiment_key = 'reminder_cadence_v1'
  AND a.status IN ('kept','no_show','rebooked','cancelled')
GROUP BY ab.variant;
