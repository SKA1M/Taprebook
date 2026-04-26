"""ETL orchestration: the top-level extract → transform → load pipeline."""
from __future__ import annotations

from taprebook.db import get_connection, apply_schema
from taprebook.etl.extract import load_all_sample
from taprebook.etl.load import load_dimensions, load_facts


def run(verbose: bool = True) -> dict[str, dict[str, int]]:
    """End-to-end pipeline: apply schema, load sample CSVs into SQLite."""
    data = load_all_sample()

    with get_connection() as conn:
        apply_schema(conn)
        dim_counts = load_dimensions(conn, data)
        fact_counts = load_facts(conn, data)

    summary = {"dimensions": dim_counts, "facts": fact_counts}
    if verbose:
        print("ETL complete.")
        for category, counts in summary.items():
            print(f"  {category}:")
            for table, n in counts.items():
                print(f"    {table:20s} {n:>6d} rows")
    return summary


if __name__ == "__main__":
    run()
