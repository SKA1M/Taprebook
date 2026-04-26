# KPI definitions

Every metric the dashboard shows is defined here. If a number looks weird, this is the first place to check.

## No-show rate

```
no_show_rate = no_shows / terminal_appts
```

**`terminal_appts`** = appointments where `status ∈ {kept, rebooked, no_show, cancelled}`.
**Excludes** `scheduled` — including it would make the rate mechanically drop whenever the forward book fills up, which is misleading.

View: `v_monthly_no_show_rate`
Query: `sql/queries/no_show_rate_monthly.sql` (also computes MoM delta with `LAG()`)

## Kept rate

```
kept_rate = kept / terminal_appts
```

Same denominator rule as no-show rate. This is what the A/B test uses as the primary outcome.

## Review conversion

```
review_conversion = review_left / review_sent
```

`review_sent` counts `events.event_type = 'review_sent'` (one REVIEW_v1 send).
`review_left` counts `events.event_type = 'review_left'` (patient replied affirmatively or the GBP webhook fired).

Query: `sql/queries/monthly_kpi_summary.sql`

## Template delivery / read / reply rates

Three conditional rates, each conditioned on the previous stage:

```
delivery_rate = delivered / sent
read_rate     = read      / delivered
reply_rate    = replied   / read
```

The view `v_template_health` also flags templates as `INVESTIGATE` (`delivery_rate < 85%`) or `REVIEW_COPY` (`read_rate < 40%`) so drift surfaces without a human staring at the numbers.

## Funnel end-to-end

```
end_to_end = kept / reminders_sent
```

Reads as: of all the appointments we reminded, what fraction were actually kept. This differs from no-show rate because it excludes walk-ins and appointments that didn't receive a reminder (e.g., booked <24h out).

Query: `sql/queries/funnel_conversion.sql`

## Cohort retention (M+6)

```
retention_m6 = (patients from cohort month M who kept an appt in month M+6) / (cohort size at M)
```

A cohort is defined by a patient's **first kept** appointment month. The M+6 horizon matches the standard dental prophylaxis recall (6 months), which is why this number is the headline retention metric — it measures whether the recall system is actually bringing people back at the clinically expected cadence.

Query: `sql/queries/cohort_recall.sql`
View: `v_cohort_recall`

## A/B: kept-rate lift

```
abs_diff = kept_rate_treatment - kept_rate_control   (percentage points)
rel_lift = abs_diff / kept_rate_control              (percent)
```

Statistical test: two-proportion z-test, two-sided, α = 0.05.
95% CI on `abs_diff` computed from separate-arm variances (Wald interval).

Implementation: `taprebook/experiments/ab_reminder_cadence.py`
Query: `sql/queries/ab_test_reminder_cadence.sql`

## Metrics we explicitly do not track

- **Revenue impact.** Synthetic data has no pricing. In production this would come from the clinic's PMS; the `events.value` column is reserved for it.
- **Patient satisfaction.** Review *counts* and *conversion* are proxies, not the same thing. A separate NPS flow would be needed.
- **Provider-level no-show rate.** The schema supports it (`appointments.provider`) but no query surfaces it yet — it's a small number of data points per provider at pilot scale and would read noisy.
