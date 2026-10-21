"""Compare every stored JSON object with the source movie files."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg

from ingest import DEFAULT_DSN, DEFAULT_SOURCE, load_files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL", DEFAULT_DSN))
    args = parser.parse_args()
    loaded = load_files(args.source)
    checked_scenes = 0
    with psycopg.connect(args.dsn) as connection:
        for path, document, _ in loaded:
            key = (document["asset_id"], document["primary_language"].upper())
            row = connection.execute(
                """SELECT source_metadata, cms_metadata, movie_gcs_path, total_scenes
                   FROM cms WHERE asset_id = %s AND primary_language = %s""",
                key,
            ).fetchone()
            if row is None:
                raise AssertionError(f"missing CMS row for {path.name}")
            expected_root = {name: value for name, value in document.items() if name != "scenes"}
            if row[0] != expected_root or row[1] != document["cms_metadata"]:
                raise AssertionError(f"CMS JSON differs from {path.name}")
            if row[2] != document["movie_gcs_path"] or row[3] != len(document["scenes"]):
                raise AssertionError(f"CMS scalar values differ from {path.name}")
            stored = connection.execute(
                """SELECT scene_data FROM scene_embeddings
                   WHERE asset_id = %s AND primary_language = %s
                   ORDER BY scene_order""",
                key,
            ).fetchall()
            if [item[0] for item in stored] != document["scenes"]:
                raise AssertionError(f"scene JSON differs from {path.name}")
            checked_scenes += len(stored)
        table_counts = connection.execute(
            "SELECT (SELECT count(*) FROM cms), (SELECT count(*) FROM scene_embeddings)"
        ).fetchone()
    print(f"Verified {len(loaded)} complete CMS documents and {checked_scenes} complete scenes")
    print(f"Database totals: cms={table_counts[0]}, scene_embeddings={table_counts[1]}")


if __name__ == "__main__":
    main()
