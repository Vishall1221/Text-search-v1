"""Search orchestration: catalog fast paths -> optional LLM -> lexical shortlist -> ranking."""

from __future__ import annotations

import threading
import time
from typing import Any

from APP.backend.query import normalized, plan_query, tokens
from APP.backend.ranking import rank_candidates
from APP.backend.repository import fetch_candidates, load_catalog
from config.settings import settings


class SearchService:
    def __init__(self) -> None:
        self._catalog: list[dict[str, Any]] = []
        self._catalog_time = 0.0
        self._lock = threading.Lock()
        self._intent_cache: dict[str, tuple[float, Any]] = {}

    def catalog(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self._catalog or time.monotonic() - self._catalog_time > settings.catalog_cache_seconds:
                self._catalog = load_catalog()
                self._catalog_time = time.monotonic()
            return list(self._catalog)

    def search(self, query: str, limit: int = 8) -> dict[str, Any]:
        started = time.monotonic()
        catalog = self.catalog()
        cache_key = normalized(query)
        with self._lock:
            cached = self._intent_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < settings.catalog_cache_seconds:
            plan = cached[1]
        else:
            plan = plan_query(query, catalog)
            with self._lock:
                if len(self._intent_cache) >= 1000:
                    self._intent_cache.clear()
                self._intent_cache[cache_key] = (time.monotonic(), plan)

        matching_catalog = [
            c for c in catalog
            if (not plan.language or c["primary_language"] == plan.language)
            and (
                (plan.title and normalized(c["title"]) == normalized(plan.title))
                or any(normalized(a) == normalized(cast) for a in plan.actors for cast in c["cast_names"])
                or any(normalized(g) == normalized(genre) for g in plan.genres for genre in c["genres"])
                or (plan.language and not (plan.title or plan.actors or plan.genres or plan.raw_terms or plan.scene_terms))
            )
        ]
        asset_ids = list(dict.fromkeys(c["asset_id"] for c in matching_catalog))
        term_source = plan.raw_terms + plan.scene_terms
        terms = list(dict.fromkeys(
            t for value in term_source for t in ([value] if " " in value else tokens(value))
            if len(t) >= 2
        ))[:12]
        rows = fetch_candidates(
            # The source's recognized-title query is targeted. Scene terms
            # rank scenes within that title; they must not pull other films.
            terms=[] if plan.title and asset_ids else terms,
            asset_ids=asset_ids,
            language=plan.language,
            broad=bool(plan.language and not terms and not asset_ids),
        )
        cards = rank_candidates(rows, plan, limit)
        # Preserve the source's high-confidence cut: a strong title/cast hit
        # suppresses weak incidental matches from another movie.
        if any(card["match_score"] >= 0.90 for card in cards):
            cards = [card for card in cards if card["match_score"] >= 0.88]
        return {
            "query": query,
            "route": plan.route,
            "llm_used": plan.llm_used,
            "llm_available": plan.llm_available,
            "extracted": {
                "title": plan.title,
                "actors": plan.actors,
                "genres": plan.genres,
                "content_language": plan.language,
                "scene_terms": plan.scene_terms,
            },
            "candidate_scenes": len(rows),
            "matched_titles": cards,
            "total_results": len(cards),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        }


search_service = SearchService()
