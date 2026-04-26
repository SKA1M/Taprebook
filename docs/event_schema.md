# Event schema

Every state-changing thing in TapRebook emits a row in the `events` table. This log is append-only and is the source of truth for everything downstream — dashboards, the monthly KPI email, and A/B analyses all derive from it.

## Columns

| Column | Type | Notes |
|---|---|---|
| `event_id` | INTEGER PK | autoincrement |
| `event_ts` | TEXT | ISO-8601, UTC-naive |
| `clinic_id` | TEXT | FK → `clinics` |
| `patient_id` | TEXT | FK → `patients`; nullable for events fired pre-identification |
| `appt_id` | TEXT | FK → `appointments`; nullable for non-appointment events |
| `event_type` | TEXT | see taxonomy below |
| `service` | TEXT | denormalized for faster filtering |
| `outcome` | TEXT | terminal-state marker (`kept`, `noshow`, `review_left`, …) |
| `value` | REAL | reserved for future monetary events (deposits, refunds) |
| `wa_sent` | INTEGER | boolean |
| `wa_delivered` | INTEGER | boolean |
| `wa_read` | INTEGER | boolean |
| `notes` | TEXT | free-form |

## Event type taxonomy

Events are named `<phase>_<action>` where practical:

### Appointment lifecycle

| `event_type` | When it fires | Typical `outcome` |
|---|---|---|
| `confirm` | CONFIRM_v1 sent at booking | — |
| `remind_d1` | REM24_v1 sent 24h before | — |
| `remind_t3h` | REM3H_v1 sent 3h before (treatment arm only) | — |
| `late` | Patient taps "Running Late" or types LATE | — |
| `reschedule` | Patient picks a new slot | — |
| `checkin` | Front desk marks arrived | — |
| `noshow` | Manual or overdue-rule triggered | `noshow` or `rebooked` |

### Review lifecycle

| `event_type` | When it fires | Typical `outcome` |
|---|---|---|
| `review_sent` | REVIEW_v1 sent post-visit | — |
| `review_left` | Patient confirms review or GBP webhook | `review_left` |

### Handoff / operations

| `event_type` | When it fires |
|---|---|
| `handoff` | `/handoff` saved reply fired (human takeover) |
| `after_hours` | `/after_hours` auto-reply fired |

## Why `events` AND `template_sends` both exist

They look redundant but serve different purposes:

- `template_sends` is the **outbound-message log** — one row per API call to Interakt. Feeds delivery/read/reply rates per template. Always has a `template_id`.
- `events` is the **state-change log** — broader than template sends. Covers things a template send didn't cause (walk-ins, manual front-desk overrides, review-link clicks).

An outbound REM24_v1 shows up in both. A patient marked no-show by the overdue rule shows up only in `events`. A review actually left shows up only in `events`.

## Rebuilding state from events

The `appointments.status` column is materialized for query speed, but it's always reconstructible from the event log:

```
latest_event_per_appt := argmax(event_ts) partition by appt_id
if latest.event_type in ('noshow', 'reschedule', 'cancel'): → that status
elif latest.outcome == 'kept':                              → 'kept'
elif now() > scheduled_at + grace:                          → 'no_show' (overdue)
else:                                                       → 'scheduled'
```

This is exactly what `derive_effective_status()` in `taprebook/etl/transform.py` does — a port of the `Master!K2` `ARRAYFORMULA` from the Google Sheets prototype. The formula lives in `docs/artifacts/google_sheets_etl.sql` for reference.
