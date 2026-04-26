-- =====================================================================
-- funnel_conversion.sql
-- Reminder-to-kept funnel with per-step conversion rates.
-- Useful for spotting where we lose patients (e.g. delivered but not read,
-- or read but not kept).
-- =====================================================================
WITH f AS (
    SELECT
        clinic_id,
        SUM(reminders_sent) AS sent,
        SUM(delivered)      AS delivered,
        SUM(read_count)     AS read_count,
        SUM(kept)           AS kept
    FROM v_reminder_funnel
    GROUP BY clinic_id
)
SELECT
    clinic_id,
    sent,
    delivered,
    read_count,
    kept,
    ROUND(100.0 * delivered  / NULLIF(sent,      0), 2) AS delivered_rate_pct,
    ROUND(100.0 * read_count / NULLIF(delivered, 0), 2) AS read_rate_pct,
    ROUND(100.0 * kept       / NULLIF(read_count,0), 2) AS kept_after_read_pct,
    ROUND(100.0 * kept       / NULLIF(sent,      0), 2) AS end_to_end_pct
FROM f
ORDER BY clinic_id;
