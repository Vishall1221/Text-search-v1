"""Read-only PostgreSQL access to the two existing source tables."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from config.settings import settings


CATALOG_SQL = """
SELECT asset_id, primary_language, title, movie_gcs_path, description,
       genres, cast_names, thumbnail_image_url, total_scenes, cms_metadata
FROM cms ORDER BY title, primary_language
"""

SCENE_COLUMNS = """
SELECT c.asset_id, c.primary_language, c.title, c.movie_gcs_path,
       c.description AS movie_description, c.genres, c.cast_names AS movie_cast,
       c.thumbnail_image_url, c.total_scenes,
       s.scene_id, s.scene_order, s.chunk_id, s.start_time, s.end_time,
       s.start_seconds, s.end_seconds, s.description, s.master_scene_summary,
       s.visual_summary, s.dialogue_transcript, s.important_dialogue,
       s.mood, s.action_intensity, s.barc_retention_score,
       s.engaging_score, s.energy_level, s.cast_names AS scene_cast,
       s.entities_characters, s.entities_objects, s.tags, s.search_text
FROM cms c
JOIN scene_embeddings s
  ON s.asset_id = c.asset_id AND s.primary_language = c.primary_language
"""


def load_catalog() -> list[dict[str, Any]]:
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        return list(conn.execute(CATALOG_SQL).fetchall())


def fetch_candidates(
    *,
    terms: list[str],
    asset_ids: list[str],
    language: str | None,
    broad: bool = False,
) -> list[dict[str, Any]]:
    """SQL shortlist: up to 60 scenes/title and 250 scenes overall.

    The scene search includes descriptions and summaries through search_text.
    All values are bound parameters. This is lexical only; embeddings are not read.
    """
    clauses: list[str] = []
    values: list[Any] = []
    if asset_ids:
        clauses.append("c.asset_id = ANY(%s::text[])")
        values.append(asset_ids)
    for term in terms[:12]:
        if len(term.strip()) >= 2:
            clauses.append("(s.search_text ILIKE %s OR c.title ILIKE %s OR c.description ILIKE %s)")
            pattern = f"%{term}%"
            values.extend((pattern, pattern, pattern))
    if not clauses and not broad:
        return []
    where = "(" + " OR ".join(clauses) + ")" if clauses else "TRUE"
    if language:
        where += " AND c.primary_language = %s"
        values.append(language)
    sql = f"""
    WITH ranked AS (
        SELECT q.*, row_number() OVER (
            PARTITION BY q.asset_id, q.primary_language ORDER BY q.scene_order
        ) AS scene_number
        FROM ({SCENE_COLUMNS} WHERE {where}) AS q
    )
    SELECT * FROM ranked WHERE scene_number <= %s
    ORDER BY scene_number, title, primary_language
    LIMIT %s
    """
    values.extend((settings.scenes_per_title, settings.candidate_limit))
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        return list(conn.execute(sql, values).fetchall())
