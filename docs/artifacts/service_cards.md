# Service cards (Interakt-ready)

*Preserved from the original pilot collateral — maps each service to the trigger, template, variables, buttons, and follow-on.*

## Confirmations & Reminders

- **Trigger:** New booking approved; D-1 and T-3h schedules
- **Templates:** `CONFIRM_v1`, `REM24_v1`, `REM3H_v1`
- **Variables:** `1=Patient, 2=Service/Doctor, 3=Date, 4=Time, 5=Address/Maps, 6=Maps URL`
- **Buttons:** Confirm (QR), Reschedule (QR), Cancel (QR), Directions (URL)
- **Follow-on:** On Reschedule → `RESCHED_AUTO_v1` (link) or `RESCHED_MAN_v1` (windows) → `RESCHEDULE_CONFIRM_v1`

## Running-late triage

- **Trigger:** Patient taps "Running late" or types LATE
- **Templates:** `LATE_v1`
- **Variables:** `1=Grace minutes`
- **Buttons:** Keep today (QR), Move later (QR)
- **Follow-on:** If Move later → `RESCHED_AUTO_v1` or slot options; tag `late`

## Self-serve rescheduling

- **Trigger:** Reschedule button from confirm/reminder/late
- **Templates:** `RESCHED_AUTO_v1`, `RESCHED_MAN_v1`
- **Variables:** AUTO: `1=Service/Doctor, 2=Booking URL`; MAN: `1=Service/Doctor, 2=Date`
- **Buttons:** AUTO: Book new time (URL); MAN: Morning/Afternoon/Evening (QR)
- **Follow-on:** After selection → propose 2–3 exact slots → `RESCHEDULE_CONFIRM_v1`

## No-show recovery

- **Trigger:** Marked "No-show" (manual or overdue rule)
- **Templates:** `NOSHOW_REBOOK_v1`
- **Variables:** `1=Patient, 2=Service/Doctor, 3=Slot A, 4=Slot B`
- **Buttons:** Book {{3}} (QR), Book {{4}} (QR), See more times (QR)
- **Follow-on:** On booking → `RESCHEDULE_CONFIRM_v1`; tag `rebooked`

## Post-visit reviews (Marketing)

- **Trigger:** 2–4h after checkout; optional nudge at 5–7 days
- **Templates:** `REVIEW_v1`
- **Variables:** `1=Patient, 2=Clinic, 3=GBP review URL`
- **Buttons:** Leave a review (URL)
- **Follow-on:** If review confirmed → tag `review_left`

## Recall / Re-open (Marketing)

- **Trigger:** 3–6 months since last visit or by service cadence
- **Templates:** `REOPEN_v1`
- **Variables:** `1=Service/Doctor, 2=Deep link/booking`
- **Buttons:** Yes hold a slot (QR), Share next week slots (QR), Not now (QR)
- **Follow-on:** If Yes → propose slots → `RESCHEDULE_CONFIRM_v1`; tag `recall_sent`

## Treatment-plan follow-ups

- **Trigger:** 24–72h after estimate shared
- **Templates:** `TR_TxPlan_Followup_v1`
- **Variables:** `1=Patient, 2=Treatment name`
- **Buttons:** Call me (QR), Share slots (QR), Later (QR)
- **Follow-on:** If Call me → alert desk; if slots → propose → `RESCHEDULE_CONFIRM_v1`
