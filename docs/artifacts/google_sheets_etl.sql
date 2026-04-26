-- =====================================================================
-- google_sheets_etl.sql — the original prototype logic, preserved.
--
-- This file captures the Google Sheets ARRAYFORMULA / QUERY logic from
-- the initial prototype (TapRebook_GS_Formulas.txt) for historical reference
-- and as a traceability map: each block below is annotated with the SQL /
-- Python function that replaced it.
--
-- This is NOT executable SQL. Google Sheets syntax (ARRAYFORMULA, QUERY,
-- REGEXREPLACE, REGEXMATCH) is preserved verbatim so the port is auditable.
-- =====================================================================

-- ---------------------------------------------------------------------
-- CheckIn!N: Phone → E.164 normalization
-- Ported to: taprebook.etl.transform.normalize_phone()
-- Replaced in SQL by: CHECK constraint + application-level normalization
--   (phones are normalized BEFORE they reach the DB)
-- ---------------------------------------------------------------------
-- =ARRAYFORMULA(IF(ROW(C2:C)=2,"Phone_E164",
--  IF(C2:C="","",
--   IF(LEFT(TRIM(C2:C),1)="+", TRIM(C2:C),
--      "+91"&REGEXREPLACE(TRIM(C2:C),"[^0-9]","")
--   )
--  )))


-- ---------------------------------------------------------------------
-- CheckIn!O: Appt_DateTime (combine date + time, fall back to timestamp)
-- Ported to: application-level composition (transform.py)
-- Replaced in SQL by: single `scheduled_at TEXT` column in `appointments`
-- ---------------------------------------------------------------------
-- =ARRAYFORMULA(
--  IF(ROW(E2:E)=2,"Appt_DateTime",
--   IF(E2:E="","",
--     IF(F2:F="Scheduled",
--        E2:E + G2:G,
--        IF(LEN(H2:H),
--           E2:E + H2:H,
--           A2:A
--        )
--     )
--   )
--  )
-- )


-- ---------------------------------------------------------------------
-- Master!A: Composite appointment ID
-- Ported to: taprebook.etl.transform.make_appt_id()
-- Replaced in SQL by: TEXT PRIMARY KEY on appointments.appt_id
-- ---------------------------------------------------------------------
-- =ARRAYFORMULA(IF(CheckIn!N2:N="","",
--  CheckIn!N2:N & "|" &
--  TEXT(INT(CheckIn!O2:O),"yyyymmdd") & "|" &
--  TEXT(CheckIn!O2:O,"hhmm")
-- ))


-- ---------------------------------------------------------------------
-- Master!K: Effective_Status (THE hardest part of the GS prototype)
-- Looks up latest check-out update; falls back to "scheduled".
-- Ported to: taprebook.etl.transform.derive_effective_status()
-- Replaced in SQL by: appointments.status column, updated via triggers
--                     at application layer; overdue rule fires in a cron.
-- ---------------------------------------------------------------------
-- =ARRAYFORMULA(IF(A2:A="","",
--  IFNA(
--   VLOOKUP(
--     A2:A,
--     SORT(QUERY({CheckOut_Updates!U2:U, CheckOut_Updates!A2:A, CheckOut_Updates!F2:F},
--                "select Col1, Col2, Col3 where Col1 is not null",0),2,FALSE),
--     3, FALSE
--   ),
--  "scheduled"
--  )))


-- ---------------------------------------------------------------------
-- Master!N, O, P: Recall due-date computation
-- "Prophy (Cleaning)" → completed_date + 180 days
-- "New Exam"          → completed_date + 365 days
-- Next_Due            → earliest non-blank of the two
-- Ported to: taprebook.etl.transform.compute_recall_dates()
-- Replaced in SQL by: computed columns in a views layer (not yet added
--                     because pilot clinics don't track procedures cleanly enough)
-- ---------------------------------------------------------------------
-- Master!N2 (Cleaning_Due):
-- =ARRAYFORMULA(IF(A2:A="","",
--  IF(K2:K="completed",
--   IF(REGEXMATCH(IFERROR(M2:M,""), "(?i)\bProphy \(Cleaning\)\b"),
--      L2:L + 180, ),
--   )
-- ))
--
-- Master!O2 (Exam_Due):
-- =ARRAYFORMULA(IF(A2:A="","",
--  IF(K2:K="completed",
--   IF(REGEXMATCH(IFERROR(M2:M,""), "(?i)\bNew Exam\b"),
--      L2:L + 365, ),
--   )
-- ))
--
-- Master!P2 (Next_Due):
-- =ARRAYFORMULA(IF(A2:A="","",
--  IF((N2:N="")*(O2:O=""),,
--    IF(N2:N="", O2:O,
--      IF(O2:O="", N2:N, IF(N2:N<=O2:O, N2:N, O2:O))
--    )
--  )))


-- ---------------------------------------------------------------------
-- Master!X, Y: Overdue_Time + Overdue_NoShow flag
-- Flags currently-scheduled appts that have passed (scheduled_at + grace)
-- Ported to: taprebook.etl.transform.derive_effective_status() (grace_minutes param)
-- Replaced in SQL by: WHERE clause in the overdue-sweep job
-- ---------------------------------------------------------------------
-- X2 (Overdue_Time): =ARRAYFORMULA(IF(A2:A="","", E2:E + W2:W/1440))
-- Y2 (Overdue_NoShow): =ARRAYFORMULA(IF(A2:A="","",
--     (K2:K="scheduled") * (NOW() > X2:X)
-- ))


-- ---------------------------------------------------------------------
-- Actions_NoShow / Reminders_Today / Reminders_Tomorrow / Recalls_30d
-- Ported to: sql/queries/*.sql + the Streamlit dashboard
-- ---------------------------------------------------------------------
-- =FILTER(Master!A:V, Master!Y:Y=TRUE)
-- =FILTER(Master!A:V, Master!K:K="scheduled", INT(Master!E:E)=TODAY())
-- =FILTER(Master!A:V, Master!K:K="scheduled", INT(Master!E:E)=TODAY()+1)
-- =FILTER(Master!A:V, Master!P:P>=TODAY(), Master!P:P<=TODAY()+30)

-- =====================================================================
-- END — Google Sheets prototype logic preserved for traceability.
-- All behavior above is now covered by unit tests in tests/test_transform.py.
-- =====================================================================
