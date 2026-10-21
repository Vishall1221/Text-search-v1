"""Validate and ingest movie-analysis JSON into the two v1 PostgreSQL tables.

The complete top-level object (except its scene array) and each complete scene
are retained in JSONB. Re-running the script updates rows without duplicates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb


DEFAULT_SOURCE = Path.home() / "Desktop" / "Datas" / "output"
DEFAULT_DSN = "postgresql://ai_search@127.0.0.1:5432/ai_search"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env", override=False)


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def cast_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        name = item if isinstance(item, str) else item[0] if isinstance(item, list) and item else None
        if isinstance(name, str) and name.strip() and name not in names:
            names.append(name)
    return names


def search_text(scene: dict[str, Any]) -> str:
    parts: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
        elif isinstance(value, list):
            for item in value:
                add(item)

    for key in (
        "description", "master_scene_summary", "visual_summary",
        "dialogue_transcript", "important_dialogue", "mood", "act_name",
        "cast", "entities", "entities_characters", "entities_objects",
        "tags", "dialogue_tokens",
    ):
        add(scene.get(key))
    for event in scene.get("events") or []:
        if isinstance(event, dict):
            add(event.get("tag"))
            add(event.get("description"))
    for moment in scene.get("key_moments") or []:
        if isinstance(moment, dict):
            add(moment.get("type"))
            add(moment.get("label"))
    for nested_key, fields in (
        ("visual", ("setting", "actions/Theme", "camera")),
        ("audio", ("transcript", "audio_events", "music_mood")),
        ("narrative_beat", ("beat", "label")),
    ):
        nested = scene.get(nested_key)
        if isinstance(nested, dict):
            for field in fields:
                add(nested.get(field))
    for emotion in scene.get("emotions") or []:
        if isinstance(emotion, dict):
            add(emotion.get("emotion"))
    return " | ".join(parts)


def load_files(source: Path) -> list[tuple[Path, dict[str, Any], str]]:
    if not source.is_dir():
        raise ValueError(f"source directory does not exist: {source}")
    files = sorted(source.glob("*.json"))
    if not files:
        raise ValueError(f"no JSON files found in {source}")
    loaded: list[tuple[Path, dict[str, Any], str]] = []
    media_keys: set[tuple[str, str]] = set()
    for path in files:
        raw = path.read_bytes()
        try:
            document = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object)
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid JSON in {path.name}: {exc}") from exc
        if not isinstance(document, dict):
            raise ValueError(f"{path.name}: root must be a JSON object")
        asset_id = document.get("asset_id")
        title = document.get("title")
        language = document.get("primary_language")
        gcs_path = document.get("movie_gcs_path")
        metadata = document.get("cms_metadata")
        scenes = document.get("scenes")
        if not all(isinstance(v, str) and v.strip() for v in (asset_id, title, language, gcs_path)):
            raise ValueError(f"{path.name}: asset_id, title, primary_language and movie_gcs_path are required")
        if not gcs_path.startswith("gs://"):
            raise ValueError(f"{path.name}: movie_gcs_path must start with gs://")
        if not isinstance(metadata, dict) or not isinstance(scenes, list):
            raise ValueError(f"{path.name}: cms_metadata must be an object and scenes must be an array")
        if metadata.get("asset_id") not in (None, asset_id):
            raise ValueError(f"{path.name}: CMS asset_id differs from root asset_id")
        media_key = (asset_id, language.upper())
        if media_key in media_keys:
            raise ValueError(f"{path.name}: duplicate asset/language pair {media_key}")
        media_keys.add(media_key)
        if document.get("total_scenes") != len(scenes):
            raise ValueError(f"{path.name}: declared total_scenes differs from scene array length")
        scene_ids: set[str] = set()
        for index, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict) or not isinstance(scene.get("scene_id"), str) or not scene["scene_id"]:
                raise ValueError(f"{path.name}: scene {index} needs a scene_id")
            if scene["scene_id"] in scene_ids:
                raise ValueError(f"{path.name}: duplicate scene_id {scene['scene_id']}")
            scene_ids.add(scene["scene_id"])
            start, end = scene.get("start_seconds"), scene.get("end_seconds")
            if (isinstance(start, bool) or isinstance(end, bool)
                    or not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                    or end <= start):
                raise ValueError(f"{path.name}: invalid times for {scene['scene_id']}")
        loaded.append((path, document, hashlib.sha256(raw).hexdigest()))
    return loaded


CMS_UPSERT = """
INSERT INTO cms (
    asset_id, primary_language, title, movie_gcs_path, description,
    genres, cast_names, thumbnail_image_url, total_chunks, total_scenes,
    processed_at, cms_metadata, source_metadata, source_file, source_sha256
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (asset_id, primary_language) DO UPDATE SET
    title = EXCLUDED.title,
    movie_gcs_path = EXCLUDED.movie_gcs_path,
    description = EXCLUDED.description,
    genres = EXCLUDED.genres,
    cast_names = EXCLUDED.cast_names,
    thumbnail_image_url = EXCLUDED.thumbnail_image_url,
    total_chunks = EXCLUDED.total_chunks,
    total_scenes = EXCLUDED.total_scenes,
    processed_at = EXCLUDED.processed_at,
    cms_metadata = EXCLUDED.cms_metadata,
    source_metadata = EXCLUDED.source_metadata,
    source_file = EXCLUDED.source_file,
    source_sha256 = EXCLUDED.source_sha256,
    ingested_at = now()
"""

SCENE_UPSERT = """
INSERT INTO scene_embeddings (
    asset_id, primary_language, scene_id, scene_order, chunk_id,
    start_time, end_time, start_seconds, end_seconds, duration_seconds,
    description, master_scene_summary, visual_summary, dialogue_transcript,
    important_dialogue, mood, action_intensity, barc_retention_score,
    engaging_score, energy_level, cast_names, entities_characters,
    entities_objects, tags, search_text, scene_data
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
ON CONFLICT (asset_id, primary_language, scene_id) DO UPDATE SET
    scene_order = EXCLUDED.scene_order,
    chunk_id = EXCLUDED.chunk_id,
    start_time = EXCLUDED.start_time,
    end_time = EXCLUDED.end_time,
    start_seconds = EXCLUDED.start_seconds,
    end_seconds = EXCLUDED.end_seconds,
    duration_seconds = EXCLUDED.duration_seconds,
    description = EXCLUDED.description,
    master_scene_summary = EXCLUDED.master_scene_summary,
    visual_summary = EXCLUDED.visual_summary,
    dialogue_transcript = EXCLUDED.dialogue_transcript,
    important_dialogue = EXCLUDED.important_dialogue,
    mood = EXCLUDED.mood,
    action_intensity = EXCLUDED.action_intensity,
    barc_retention_score = EXCLUDED.barc_retention_score,
    engaging_score = EXCLUDED.engaging_score,
    energy_level = EXCLUDED.energy_level,
    cast_names = EXCLUDED.cast_names,
    entities_characters = EXCLUDED.entities_characters,
    entities_objects = EXCLUDED.entities_objects,
    tags = EXCLUDED.tags,
    search_text = EXCLUDED.search_text,
    embedding = CASE WHEN scene_embeddings.scene_data IS DISTINCT FROM EXCLUDED.scene_data
        THEN NULL ELSE scene_embeddings.embedding END,
    embedding_model = CASE WHEN scene_embeddings.scene_data IS DISTINCT FROM EXCLUDED.scene_data
        THEN NULL ELSE scene_embeddings.embedding_model END,
    scene_data = EXCLUDED.scene_data,
    ingested_at = now()
"""


def ingest(connection: psycopg.Connection[Any], loaded: list[tuple[Path, dict[str, Any], str]]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        for path, document, digest in loaded:
            metadata = document["cms_metadata"]
            language = document["primary_language"].upper()
            source_metadata = {key: value for key, value in document.items() if key != "scenes"}
            processed = document.get("processed_at")
            processed_at = datetime.fromisoformat(processed.replace("Z", "+00:00")) if processed else None
            cursor.execute(
                CMS_UPSERT,
                (
                    document["asset_id"], language, document["title"], document["movie_gcs_path"],
                    metadata.get("description") or document.get("plot_synopsis"),
                    strings(metadata.get("genre") or document.get("genre")),
                    cast_names(metadata.get("cast_info") or document.get("cast_info")),
                    metadata.get("thumbnail_image_url"), document.get("total_chunks"),
                    len(document["scenes"]), processed_at, Jsonb(metadata),
                    Jsonb(source_metadata), path.name, digest,
                ),
            )
            for order, scene in enumerate(document["scenes"], start=1):
                cursor.execute(
                    SCENE_UPSERT,
                    (
                        document["asset_id"], language, scene["scene_id"], order, scene.get("chunk_id"),
                        scene.get("start_time"), scene.get("end_time"), scene["start_seconds"],
                        scene["end_seconds"], scene.get("duration_seconds"), scene.get("description"),
                        scene.get("master_scene_summary"), scene.get("visual_summary"),
                        scene.get("dialogue_transcript"), scene.get("important_dialogue"),
                        scene.get("mood"), scene.get("action_intensity"),
                        scene.get("barc_retention_score"), scene.get("engaging_score"),
                        scene.get("energy_level"), cast_names(scene.get("cast")),
                        strings(scene.get("entities_characters")), strings(scene.get("entities_objects")),
                        strings(scene.get("tags")), search_text(scene), Jsonb(scene),
                    ),
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="directory containing movie JSON files")
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL", DEFAULT_DSN), help="PostgreSQL connection string")
    parser.add_argument("--dry-run", action="store_true", help="validate files without connecting or writing")
    args = parser.parse_args()
    loaded = load_files(args.source)
    count = sum(len(document["scenes"]) for _, document, _ in loaded)
    print(f"Validated {len(loaded)} movie files and {count} scenes from {args.source}")
    if args.dry_run:
        return
    with psycopg.connect(args.dsn) as connection:
        ingest(connection, loaded)
    print(f"Ingested {len(loaded)} CMS rows and {count} scene rows")


if __name__ == "__main__":
    main()
