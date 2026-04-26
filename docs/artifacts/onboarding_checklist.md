# Clinic onboarding checklist

*The sign-up → go-live runbook used for the Kochi pilots.*

## Pre-launch

- [ ] Intake form submitted (logo, hours, phones, links)
- [ ] Decide path: Automated (Google/Calendly) **OR** Manual (time windows, SLA)
- [ ] WhatsApp number ready; Meta Business / WABA onboarding complete
- [ ] Interakt account: add WhatsApp number, complete embedded signup

## Templates

- [ ] Approve Utility templates first: `CONFIRM_v1`, `REM24_v1`, `REM3H_v1`, `LATE_v1`, `RESCHED_AUTO_v1`, `RESCHED_MAN_v1`, `NOSHOW_REBOOK_v1`, `RESCHEDULE_CONFIRM_v1`, `REOPEN_v1`
- [ ] Then Marketing: `REVIEW_v1`, recall variants
- [ ] After-hours auto-reply set
- [ ] Saved replies loaded: `/handoff`, `/offer`, `/confirm`, `/after_hours`

## Booking + config

- [ ] Booking link (Practo/Calendly/PMS or Google Appointments) connected
- [ ] Reminder windows configured: D-1, D-0 (T-3h) + grace minutes
- [ ] Review link (Google Business Profile) verified per location
- [ ] Maps link + calendar/ICS link stored

## Patient data

- [ ] Patient list intake received (Sheet/Excel export/photos acceptable)
- [ ] Minimum fields present: Name, Phone (+91 E.164)
- [ ] Data Processing Addendum signed
- [ ] Initial cohort tagged (e.g., `pilot_batch_YYYYMM`)

## Tags mapped

- [ ] `confirmed`, `reminded_d-1`, `reminded_d0`
- [ ] `late`, `noshow`, `rebooked`
- [ ] `review_sent`, `review_left`
- [ ] `recall_sent`, `tx_followup`

## Go-live

- [ ] Test flow end-to-end (self): Confirm → Reminders → Resched → Late → Review
- [ ] KPI snapshot wiring verified; monthly email/dashboard per plan
- [ ] Go-live date set (first Monday after approvals)
- [ ] Pilot metrics agreed: no-show %, rebooks, reviews
- [ ] Weekly sanity check scheduled for first 2 weeks

## Daily ops (15 min)

Clear threads breaching SLA · scan LATE · scan inside-cutoff reschedules.

## Weekly ops (30 min)

Export KPI snapshot · review delivery/read rates · tweak one line if needed.
