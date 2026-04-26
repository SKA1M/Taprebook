"""Initialize the SQLite warehouse: schema + views + sample data.

Usage:
    python scripts/init_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running without installing the package
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from taprebook.config import DB_PATH, SAMPLE_DIR
from taprebook.data_gen.generate import generate as generate_data
from taprebook.etl.run_pipeline import run as run_etl


def main() -> None:
    # Generate sample CSVs if missing
    if not (SAMPLE_DIR / "appointments.csv").exists():
        print("Sample data missing — generating...")
        generate_data()

    # Delete existing DB for a clean rebuild
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Removed existing {DB_PATH}")

    print(f"Initializing {DB_PATH}")
    run_etl()
    print(f"✔ Done. Database at: {DB_PATH}")


if __name__ == "__main__":
    main()
