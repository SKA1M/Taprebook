"""A/B analysis: reminder_cadence_v1.

Experiment design
-----------------
Hypothesis  : Adding a T-3h same-day reminder on top of the standard D-1
              reminder increases kept-appointment rate.
Unit        : Appointment (not patient — patients can be in both arms
              across different visits; we control for that by randomizing
              at the appointment level at assignment time).
Arms        :
    * control    — REM24_v1 only          (D-1 reminder)
    * treatment  — REM24_v1 + REM3H_v1    (D-1 + T-3h reminders)
Primary KPI : kept_rate = P(status = 'kept' | terminal status)
Test        : Two-proportion z-test, two-sided, alpha=0.05
              Reported with absolute diff, relative lift, and 95% CI.

Usage
-----
    python -m taprebook.experiments.ab_reminder_cadence
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd
from scipy import stats

from taprebook.db import get_connection, run_query_file


@dataclass
class ABResult:
    control_n: int
    control_kept: int
    control_rate: float
    treatment_n: int
    treatment_kept: int
    treatment_rate: float
    absolute_diff_pct: float
    relative_lift_pct: float
    z_stat: float
    p_value: float
    ci_95_low: float
    ci_95_high: float
    significant: bool

    def pretty(self) -> str:
        sig = "YES ✅" if self.significant else "no"
        return (
            "A/B — reminder_cadence_v1 (D-1 vs D-1+T-3h)\n"
            "────────────────────────────────────────────\n"
            f"Control     : n={self.control_n:>4d}  kept={self.control_kept:>4d}  "
            f"rate={self.control_rate:6.2f}%\n"
            f"Treatment   : n={self.treatment_n:>4d}  kept={self.treatment_kept:>4d}  "
            f"rate={self.treatment_rate:6.2f}%\n"
            "────────────────────────────────────────────\n"
            f"Abs diff    : {self.absolute_diff_pct:+.2f} pp\n"
            f"Rel lift    : {self.relative_lift_pct:+.2f}%\n"
            f"95% CI      : [{self.ci_95_low:+.2f}, {self.ci_95_high:+.2f}] pp\n"
            f"z-statistic : {self.z_stat:+.3f}\n"
            f"p-value     : {self.p_value:.4f}\n"
            f"Significant : {sig} (alpha=0.05)"
        )


def two_proportion_z_test(
    x1: int, n1: int, x2: int, n2: int, alpha: float = 0.05
) -> tuple[float, float, float, float]:
    """Two-sided two-proportion z-test.

    Returns (z_stat, p_value, ci_low, ci_high) for (p2 − p1) in percentage points.
    """
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0, 0.0, 0.0

    p1 = x1 / n1
    p2 = x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se_pool = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2)) or 1e-12
    z = (p2 - p1) / se_pool
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))

    # Wilson-ish CI on the difference using separate-arm variance
    se_diff = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    z_crit = stats.norm.ppf(1 - alpha / 2)
    ci_low = (p2 - p1) - z_crit * se_diff
    ci_high = (p2 - p1) + z_crit * se_diff

    # Return CI in percentage points
    return z, p_value, ci_low * 100, ci_high * 100


def analyze(df: pd.DataFrame, alpha: float = 0.05) -> ABResult:
    """Compute the A/B result from the two-row variant summary DataFrame."""
    expected = {"control", "treatment"}
    variants = set(df["variant"])
    if not expected.issubset(variants):
        raise ValueError(f"DataFrame missing variants: expected {expected}, got {variants}")

    c = df[df["variant"] == "control"].iloc[0]
    t = df[df["variant"] == "treatment"].iloc[0]

    z, p, lo, hi = two_proportion_z_test(
        x1=int(c["kept"]), n1=int(c["n"]),
        x2=int(t["kept"]), n2=int(t["n"]),
        alpha=alpha,
    )

    control_rate = float(c["kept_rate_pct"])
    treatment_rate = float(t["kept_rate_pct"])

    return ABResult(
        control_n=int(c["n"]),
        control_kept=int(c["kept"]),
        control_rate=control_rate,
        treatment_n=int(t["n"]),
        treatment_kept=int(t["kept"]),
        treatment_rate=treatment_rate,
        absolute_diff_pct=treatment_rate - control_rate,
        relative_lift_pct=((treatment_rate - control_rate) / control_rate * 100)
            if control_rate else 0.0,
        z_stat=z,
        p_value=p,
        ci_95_low=lo,
        ci_95_high=hi,
        significant=p < alpha,
    )


def main() -> None:
    with get_connection() as conn:
        df = run_query_file(conn, "ab_test_reminder_cadence")

    if df.empty:
        print("No A/B data yet — run `make generate && make init-db` first.")
        return

    result = analyze(df)
    print(result.pretty())


if __name__ == "__main__":
    main()
