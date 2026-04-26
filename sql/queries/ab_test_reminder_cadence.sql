-- =====================================================================
-- ab_test_reminder_cadence.sql
-- Pulls control vs treatment summary for the reminder_cadence_v1 experiment.
--
-- Experiment design (documented in taprebook/experiments/ab_reminder_cadence.py):
--   * Control   = D-1 reminder only  (REM24_v1)
--   * Treatment = D-1 + T-3h reminders (REM24_v1 + REM3H_v1)
--   * Primary outcome = kept_rate (appt.status = 'kept')
--   * Randomization unit = appointment
--
-- Python consumes this SELECT and runs a two-proportion z-test.
-- =====================================================================
SELECT
    variant,
    n,
    kept,
    no_shows,
    kept_rate_pct
FROM v_ab_reminder_cadence
ORDER BY CASE variant WHEN 'control' THEN 1 ELSE 2 END;
