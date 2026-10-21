"""Port of the source's hand-written lexical scene and title match scores.

No vector distance, model reranker, popularity, recency, or campaign signals.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any
from urllib.parse import quote

from APP.backend.query import QueryPlan, normalized, tokens


def _matches_word(text: str, word: str) -> bool:
    # The source checks a word boundary before each token; retain that behavior.
    return bool(re.search(r"(?<!\w)" + re.escape(word), text))


def score_scene(row: dict[str, Any], content_tokens: list[str], thematic: list[str]) -> tuple[float, bool]:
    text = normalized(" ".join([
        " ".join(row.get("genres") or []),
        " ".join(row.get("movie_cast") or []),
        row.get("search_text") or "",
    ]))
    tag_text = normalized(" ".join((row.get("genres") or []) + (row.get("tags") or [])))
    high = [t for t in content_tokens if len(t) > 2]
    matched_high = [t for t in high if _matches_word(text, t)]
    matched_thematic = [t for t in thematic if len(t) > 2 and _matches_word(text, t)]
    high_phrase = " ".join(high)
    phrases = [high_phrase] + [p for p in thematic if len(p.split()) > 1]
    phrase_matched = any(len(p) >= 4 and (p in tag_text or p in text) for p in phrases if p)
    matched = phrase_matched or bool(matched_high) or bool(matched_thematic)
    base = 0.70
    if phrase_matched:
        base += 0.22
    base += min(0.20, len(matched_high) * 0.10)
    base += min(0.08, len(matched_thematic) * 0.04)
    if not matched:
        base = 0.65
    return round(min(0.99, max(0.65, base)), 2), matched


def _scene_card(row: dict[str, Any], score: float, matched: bool) -> dict[str, Any]:
    start = float(row["start_seconds"])
    end = float(row["end_seconds"])
    return {
        "scene_id": row["scene_id"],
        "chunk_id": row["chunk_id"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "start_seconds": start,
        "end_seconds": end,
        "description": row["description"],
        "master_scene_summary": row["master_scene_summary"],
        "visual_summary": row["visual_summary"],
        "dialogue_transcript": row["dialogue_transcript"],
        "important_dialogue": row["important_dialogue"],
        "mood": row["mood"],
        "action_intensity": row["action_intensity"],
        "barc_retention_score": row["barc_retention_score"],
        "engaging_score": row["engaging_score"],
        "energy_level": row["energy_level"],
        "cast": row["scene_cast"],
        "characters": row["entities_characters"],
        "objects": row["entities_objects"],
        "tags": row["tags"],
        "match_score": score,
        "is_query_match": matched,
        "playback_url": (
            f"/api/video/{quote(row['asset_id'], safe='')}?language="
            f"{quote(row['primary_language'], safe='')}&start={start:g}"
        ),
    }


def rank_candidates(rows: list[dict[str, Any]], plan: QueryPlan, limit: int) -> list[dict[str, Any]]:
    # The source's thematic tokens, minus title and language terms so a title in
    # every master_scene_summary cannot falsely make every scene a scene match.
    content_tokens = list(dict.fromkeys(plan.raw_terms + [t for p in plan.scene_terms for t in tokens(p)]))[:12]
    thematic = [normalized(p) for p in plan.scene_terms if p]
    grouped: dict[tuple[str, str], list[tuple[dict[str, Any], float, bool]]] = defaultdict(list)
    for row in rows:
        score, matched = score_scene(row, content_tokens, thematic)
        grouped[(row["asset_id"], row["primary_language"])].append((row, score, matched))

    cards: list[dict[str, Any]] = []
    for (asset_id, language), scenes in grouped.items():
        scenes.sort(key=lambda item: (item[1], item[2], -item[0]["scene_order"]), reverse=True)
        first = scenes[0][0]
        title = first["title"]
        is_exact_title = bool(plan.title and normalized(plan.title) == normalized(title))
        matched_cast = [a for a in first["movie_cast"] if any(normalized(a) == normalized(p) for p in plan.actors)]
        genre_match = any(normalized(g) == normalized(p) for g in first["genres"] for p in plan.genres)
        matched_scenes = [item for item in scenes if item[2]]

        # Do not return unrelated movies just because the database fallback
        # happened to shortlist them. Metadata-only filters remain valid.
        if not (is_exact_title or matched_cast or genre_match or matched_scenes or (plan.language and not content_tokens)):
            continue

        if is_exact_title:
            movie_score, matched_by = 0.99, f"Exact Title Match: {title}"
        elif len(matched_cast) >= 2:
            movie_score, matched_by = 0.98, f"Cast Match (#{matched_cast[0]}, #{matched_cast[1]})"
        elif len(matched_cast) == 1:
            movie_score, matched_by = 0.95, f"Cast Match (#{matched_cast[0]})"
        elif matched_scenes:
            top = max(item[1] for item in matched_scenes)
            genre_bonus = 0.03 if genre_match else 0.0
            density_bonus = min(0.06, len(matched_scenes) * 0.015)
            movie_score = round(max(0.85, min(0.96, top + genre_bonus + density_bonus)), 2)
            count = len(matched_scenes)
            matched_by = f"{count} Matching Scene Cut" if count == 1 else f"{count} Matching Scene Cuts"
        else:
            movie_score, matched_by = 0.85, "Catalog Metadata Match"

        chosen = (matched_scenes or scenes)[:5]
        cards.append({
            "asset_id": asset_id,
            "primary_language": language,
            "title": title,
            "description": first["movie_description"],
            "genres": first["genres"],
            "cast": first["movie_cast"],
            "thumbnail_image_url": first["thumbnail_image_url"],
            "movie_gcs_path": first["movie_gcs_path"],
            "total_scenes": first["total_scenes"],
            "matched_scene_count": len(matched_scenes),
            "match_score": movie_score,
            "matched_by": matched_by,
            "matched_scenes": [_scene_card(row, score, matched) for row, score, matched in chosen],
        })

    # The v1 final score is match_score alone. A title sort only breaks ties.
    cards.sort(key=lambda item: (-item["match_score"], item["title"], item["primary_language"]))
    return cards[:limit]
