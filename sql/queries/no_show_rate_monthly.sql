-- =====================================================================
-- no_show_rate_monthly.sql
-- Monthly no-show rate per clinic, with month-over-month delta.
-- Uses the v_monthly_no_show_rate view + LAG() window function.
-- =====================================================================
SELECT
    clinic_id,
    month,
    terminal_appts,
    no_shows,
    no_show_rate_pct,
    ROUND(
        no_show_rate_pct - LAG(no_show_rate_pct)
                             OVER (PARTITION BY clinic_id ORDER BY month),
        2
    ) AS mom_delta_pct
FROM v_monthly_no_show_rate
ORDER BY clinic_id, month;
