-- =====================================================================
-- cohort_recall.sql
-- Classic cohort retention table (rows=cohort_month, cols=M0..M6),
-- reported as % of cohort size that kept another appt in month N.
--
-- We PIVOT manually with conditional aggregation because SQLite has no
-- native PIVOT. The Python runner can pivot further via pandas if needed.
-- =====================================================================
WITH sizes AS (
    SELECT clinic_id, cohort_month, active_patients AS cohort_size
    FROM v_cohort_recall
    WHERE month_offset = 0
)
SELECT
    r.clinic_id,
    r.cohort_month,
    s.cohort_size,
    MAX(CASE WHEN r.month_offset = 1 THEN r.active_patients END) AS m1,
    MAX(CASE WHEN r.month_offset = 2 THEN r.active_patients END) AS m2,
    MAX(CASE WHEN r.month_offset = 3 THEN r.active_patients END) AS m3,
    MAX(CASE WHEN r.month_offset = 4 THEN r.active_patients END) AS m4,
    MAX(CASE WHEN r.month_offset = 5 THEN r.active_patients END) AS m5,
    MAX(CASE WHEN r.month_offset = 6 THEN r.active_patients END) AS m6,
    -- Retention % at M+6 (typical dental recall = ~6mo cleaning)
    ROUND(
        100.0 * MAX(CASE WHEN r.month_offset = 6 THEN r.active_patients END)
              / NULLIF(s.cohort_size, 0),
        1
    ) AS retention_m6_pct
FROM v_cohort_recall r
JOIN sizes s
  ON s.clinic_id    = r.clinic_id
 AND s.cohort_month = r.cohort_month
GROUP BY r.clinic_id, r.cohort_month, s.cohort_size
ORDER BY r.clinic_id, r.cohort_month;
