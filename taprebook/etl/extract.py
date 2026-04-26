"""ETL extract layer — read source data into DataFrames.

Sources (in order of priority as the system matures):
  1. CSV exports in data/sample/ (default for this repo)
  2. Google Sheets via sheets API (stubbed here for future work)
  3. Interakt webhook payloads stored in data/raw/webhooks/*.json
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from taprebook.config import SAMPLE_DIR


def read_csv(name: str, directory: Optional[Path] = None) -> pd.DataFrame:
    """Read a CSV from data/sample/ (or override directory)."""
    base = Path(directory) if directory else SAMPLE_DIR
    path = base / name
    if not path.exists():
        raise FileNotFoundError(
            f"CSV not found: {path}. Run `make generate` first to create sample data."
        )
    return pd.read_csv(path)


def load_all_sample() -> dict[str, pd.DataFrame]:
    """Load the full sample dataset into a dict of DataFrames."""
    return {
        "clinics":         read_csv("clinics.csv"),
        "patients":        read_csv("patients.csv"),
        "templates":       read_csv("templates.csv"),
        "appointments":    read_csv("appointments.csv"),
        "events":          read_csv("events.csv"),
        "template_sends":  read_csv("template_sends.csv"),
        "ab_assignments":  read_csv("ab_assignments.csv"),
    }
