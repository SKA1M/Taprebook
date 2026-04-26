"""Central configuration — resolved from environment variables with sane defaults.

Anything a deployment would override (DB path, API keys, clinic timezone) lives here
so other modules import a single source of truth.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Paths ------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = REPO_ROOT / "sql"
QUERIES_DIR = SQL_DIR / "queries"
DATA_DIR = REPO_ROOT / "data"
SAMPLE_DIR = DATA_DIR / "sample"
TEMPLATES_DIR = REPO_ROOT / "templates"

DB_PATH = Path(os.environ.get("TAPREBOOK_DB", DATA_DIR / "taprebook.db"))

# --- Clinic defaults --------------------------------------------------------
DEFAULT_TIMEZONE = os.environ.get("TAPREBOOK_TZ", "Asia/Kolkata")
DEFAULT_GRACE_MINUTES = int(os.environ.get("TAPREBOOK_GRACE_MINUTES", "15"))

# --- API: Interakt (WhatsApp BSP) ------------------------------------------
# Stub client reads these; real deployments would load from secret manager.
INTERAKT_API_BASE = os.environ.get("INTERAKT_API_BASE", "https://api.interakt.ai/v1")
INTERAKT_API_KEY = os.environ.get("INTERAKT_API_KEY", "")

# --- LLM triage -------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TRIAGE_MODEL = os.environ.get("TAPREBOOK_TRIAGE_MODEL", "claude-haiku-4-5-20251001")


def ensure_data_dirs() -> None:
    """Create data/ and data/sample/ if missing."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
