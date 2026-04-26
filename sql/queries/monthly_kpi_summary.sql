-- =====================================================================
-- monthly_kpi_summary.sql
-- The top-line monthly KPIs that feed the "monthly email report" mentioned
-- in the pricing one-pager (Lite plan: Monthly KPI email).
--
-- Kept, rebooks, and reviews roll up from different tables, so we do
-- three CTE aggregations and join on (clinic_id, month).
-- =====================================================================
WITH appts AS (
    SELECT
        clinic_id,
        strftime('%Y-%m', scheduled_at) AS month,
        SUM(CASE WHEN status = 'kept'     THEN 1 ELSE 0 END) AS kept,
        SUM(CASE WHEN status = 'rebooked' THEN 1 ELSE 0 END) AS rebooked,
        SUM(CASE WHEN status = 'no_show'  THEN 1 ELSE 0 END) AS no_shows,
        COUNT(*)                                             AS total_appts
    FROM appointments
    WHERE status IN ('kept','rebooked','no_show','cancelled')
    GROUP BY clinic_id, month
),
reviews AS (
    SELECT
        clinic_id,
        strftime('%Y-%m', event_ts) AS month,
        SUM(CASE WHEN event_type = 'review_sent' THEN 1 ELSE 0 END) AS review_sent,
        SUM(CASE WHEN event_type = 'review_left' THEN 1 ELSE 0 END) AS review_left
    FROM events
    WHERE event_type IN ('review_sent','review_left')
    GROUP BY clinic_id, month
)
SELECT
    c.clinic_name,
    a.month,
    a.total_appts,
    a.kept,
    a.no_shows,
    a.rebooked,
    ROUND(100.0 * a.no_shows / NULLIF(a.total_appts, 0), 1) AS no_show_rate_pct,
    COALESCE(r.review_sent, 0) AS review_sent,
    COALESCE(r.review_left, 0) AS review_left,
    ROUND(100.0 * COALESCE(r.review_left, 0)
                / NULLIF(r.review_sent, 0), 1) AS review_conversion_pct
FROM appts a
JOIN clinics c ON c.clinic_id = a.clinic_id
LEFT JOIN reviews r
       ON r.clinic_id = a.clinic_id
      AND r.month     = a.month
ORDER BY c.clinic_name, a.month;
