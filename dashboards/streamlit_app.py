"""TapRebook KPI dashboard.

Launch:
    streamlit run dashboards/streamlit_app.py

Tabs:
    1. Monthly KPI Summary     — top-line metrics per clinic
    2. No-show Trend           — rate over time + MoM delta
    3. Reminder Funnel         — sent → delivered → read → kept
    4. Cohort Recall           — retention triangle
    5. Template Health         — per-template delivery/read/reply rates
    6. A/B Test                — reminder cadence analysis
"""
from __future__ import annotations

import sys
from pathlib import Path

# Enable running `streamlit run dashboards/streamlit_app.py` from repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from taprebook.config import DB_PATH, SAMPLE_DIR
from taprebook.db import get_connection, run_query_file
from taprebook.experiments.ab_reminder_cadence import analyze as analyze_ab


st.set_page_config(page_title="TapRebook KPIs", layout="wide")

# --- Auto-initialize DB on first run (for hosted deployments) ---------------
@st.cache_resource
def _bootstrap_db():
    """Build the DB from synthetic data if it doesn't exist yet."""
    if DB_PATH.exists():
        return str(DB_PATH)
    with st.spinner("First-time setup: generating synthetic data and building warehouse…"):
        if not (SAMPLE_DIR / "appointments.csv").exists():
            from taprebook.data_gen.generate import generate as generate_data
            generate_data()
        from taprebook.etl.run_pipeline import run as run_etl
        run_etl(verbose=False)
    return str(DB_PATH)


_bootstrap_db()


@st.cache_data(ttl=60)
def _run(name: str) -> pd.DataFrame:
    with get_connection() as conn:
        return run_query_file(conn, name)


st.title("🦷 TapRebook — Clinic KPI Dashboard")
st.caption("WhatsApp receptionist analytics · Kochi pilots · synthetic demo data")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Monthly Summary",
    "No-show Trend",
    "Reminder Funnel",
    "Cohort Recall",
    "Template Health",
    "A/B: Reminder Cadence",
])

# ---------------------------------------------------------------- Tab 1
with tab1:
    st.subheader("Monthly KPI Summary")
    df = _run("monthly_kpi_summary")
    if df.empty:
        st.warning("No data. Run `make generate && make init-db` first.")
    else:
        # Top-line metrics for the most recent month
        latest_month = df["month"].max()
        latest = df[df["month"] == latest_month]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Month", latest_month)
        c2.metric("Total kept", int(latest["kept"].sum()))
        c3.metric("No-show rate", f"{latest['no_show_rate_pct'].mean():.1f}%")
        c4.metric("Reviews left", int(latest["review_left"].sum()))
        st.dataframe(df, use_container_width=True)

# ---------------------------------------------------------------- Tab 2
with tab2:
    st.subheader("No-show Rate — Monthly Trend")
    df = _run("no_show_rate_monthly")
    if df.empty:
        st.info("No data yet.")
    else:
        fig = px.line(
            df, x="month", y="no_show_rate_pct",
            color="clinic_id", markers=True,
            title="No-show rate (%) by clinic",
        )
        fig.update_yaxes(rangemode="tozero")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df, use_container_width=True)

# ---------------------------------------------------------------- Tab 3
with tab3:
    st.subheader("Reminder → Kept Funnel")
    df = _run("funnel_conversion")
    if df.empty:
        st.info("No data yet.")
    else:
        st.dataframe(df, use_container_width=True)

        # Plot one funnel per clinic (horizontal bars side-by-side)
        long = df.melt(
            id_vars="clinic_id",
            value_vars=["sent", "delivered", "read_count", "kept"],
            var_name="stage", value_name="count",
        )
        stage_order = ["sent", "delivered", "read_count", "kept"]
        long["stage"] = pd.Categorical(long["stage"], categories=stage_order, ordered=True)
        fig = px.bar(
            long.sort_values(["clinic_id", "stage"]),
            x="stage", y="count", color="clinic_id",
            barmode="group", title="Funnel volume by stage",
        )
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------- Tab 4
with tab4:
    st.subheader("Cohort Recall")
    df = _run("cohort_recall")
    if df.empty:
        st.info("No data yet.")
    else:
        clinic_choice = st.selectbox("Clinic", sorted(df["clinic_id"].unique()))
        view = df[df["clinic_id"] == clinic_choice].drop(columns="clinic_id")
        st.dataframe(view, use_container_width=True)
        st.caption(
            "m1..m6 = unique patients from that cohort who kept an appointment N months later."
        )

# ---------------------------------------------------------------- Tab 5
with tab5:
    st.subheader("Template Health")
    df = _run("template_health")
    if df.empty:
        st.info("No data yet.")
    else:
        st.dataframe(df, use_container_width=True)
        fig = px.bar(
            df.sort_values("sent", ascending=False),
            x="template_id", y=["delivery_rate_pct", "read_rate_pct", "reply_rate_pct"],
            barmode="group", title="Delivery / read / reply rates",
        )
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------- Tab 6
with tab6:
    st.subheader("A/B Test — reminder_cadence_v1")
    st.caption("Control = D-1 only · Treatment = D-1 + T-3h · Primary: kept rate")
    df = _run("ab_test_reminder_cadence")
    if df.empty:
        st.info("No data yet.")
    else:
        result = analyze_ab(df)
        c1, c2, c3 = st.columns(3)
        c1.metric("Control kept rate",   f"{result.control_rate:.2f}%",
                  f"n={result.control_n}")
        c2.metric("Treatment kept rate", f"{result.treatment_rate:.2f}%",
                  f"n={result.treatment_n}")
        c3.metric("Lift", f"{result.absolute_diff_pct:+.2f} pp",
                  f"p={result.p_value:.4f}")
        st.text(result.pretty())
