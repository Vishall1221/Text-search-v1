"""Catalog-driven fast path and optional local-LLM query extraction."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

LANGUAGE_ALIASES = {
    "bengali": "BENGALI", "বাংলা": "BENGALI", "bangla": "BENGALI",
    "hindi": "HINDI", "हिंदी": "HINDI", "hindustani": "HINDI",
    "marathi": "MARATHI", "मराठी": "MARATHI",
    "tamil": "TAMIL", "தமிழ்": "TAMIL",
    "telugu": "TELUGU", "తెలుగు": "TELUGU",
    "kannada": "KANNADA", "ಕನ್ನಡ": "KANNADA",
    "malayalam": "MALAYALAM", "മലയാളം": "MALAYALAM",
    "punjabi": "PUNJABI", "ਪੰਜਾਬੀ": "PUNJABI",
    "gujarati": "GUJARATI", "ગુજરાતી": "GUJARATI",
    "english": "ENGLISH", "bhojpuri": "BHOJPURI",
}
STOPWORDS = {
    "a", "an", "and", "are", "at", "by", "can", "find", "film", "films", "for", "from",
    "give", "in", "is", "me", "movie", "movies", "of", "on", "play", "please", "scene",
    "scenes", "search", "show", "the", "this", "to", "watch", "where", "with",
    "all", "any", "i", "want", "need", "some", "get", "find", "which", "that",
    "dikhao", "chalao", "wali", "wala", "mein", "ki", "ka", "ke", "aur", "hai",
    "कहां", "मुझे", "दिखाओ", "फिल्म", "सीन", "में", "की", "का", "और",
}


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold().replace("_", " ")).strip()


def contains_phrase(haystack: str, needle: str) -> bool:
    if not needle:
        return False
    return bool(re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", haystack))


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[^\W_]+", normalized(text), flags=re.UNICODE) if len(t) >= 2]


@dataclass
class QueryPlan:
    query: str
    title: str | None = None
    language: str | None = None
    actors: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    scene_terms: list[str] = field(default_factory=list)
    raw_terms: list[str] = field(default_factory=list)
    route: str = "lexical"
    llm_used: bool = False
    llm_available: bool = True


def _as_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [v for v in value if isinstance(v, str) and v.strip()] if isinstance(value, list) else []


def _llm_extract(query: str, catalog: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not settings.llm_enabled:
        return None
    catalog_hint = ", ".join(sorted({c["title"] for c in catalog})[:80])
    prompt = (
        "Extract search components from the user's movie-catalog query. Return one JSON object only with "
        "title (string/null), actors (array), characters (array), genres (array), "
        "content_language (string/null), scene_phrases (array), and english_scene_keywords (array). "
        "A field is a FILTER only if the user explicitly requested it. The language used to WRITE the "
        "query is NOT the requested movie language. Do not invent a title, actor, or genre. "
        "For Indian-language and mixed-language scene wording, add concise English equivalents to "
        "english_scene_keywords. No conversational answer. Known titles: " + catalog_hint
    )
    payload = {
        "model": settings.llm_model,
        "temperature": 0,
        "max_tokens": 180,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": query},
        ],
    }
    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(f"{settings.llm_base_url}/v1/chat/completions", json=payload)
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        logger.info("Local LLM unavailable or invalid output; lexical fallback: %s", exc)
        return None


def plan_query(query: str, catalog: list[dict[str, Any]]) -> QueryPlan:
    clean = normalized(query)
    plan = QueryPlan(query=query)
    if not clean:
        return plan

    for alias, canonical in LANGUAGE_ALIASES.items():
        if contains_phrase(clean, normalized(alias)):
            plan.language = canonical
            break

    titles = sorted({c["title"] for c in catalog}, key=len, reverse=True)
    for title in titles:
        if contains_phrase(clean, normalized(title)):
            plan.title = title
            break

    known_actors = sorted({a for c in catalog for a in c["cast_names"] if a}, key=len, reverse=True)
    for actor in known_actors:
        if contains_phrase(clean, normalized(actor)):
            plan.actors.append(actor)

    known_genres = sorted({g for c in catalog for g in c["genres"] if g}, key=len, reverse=True)
    for genre in known_genres:
        g = normalized(genre)
        aliases = [g]
        if g == "romance":
            aliases.append("romantic")
        if any(contains_phrase(clean, alias) for alias in aliases):
            plan.genres.append(genre)

    excluded = set(STOPWORDS)
    for value in ([plan.title] if plan.title else []) + plan.actors + plan.genres:
        excluded.update(tokens(value))
    if plan.language:
        for alias, canonical in LANGUAGE_ALIASES.items():
            if canonical == plan.language:
                excluded.update(tokens(alias))
    plan.raw_terms = list(dict.fromkeys(t for t in tokens(query) if t not in excluded))[:12]

    # Source fast path: short unambiguous title/play command needs no LLM.
    if plan.title and not plan.raw_terms and len(tokens(query)) <= 5:
        plan.route = "exact_title_fast_path"
        return plan
    # Known actor, genre, or language lookup with no scene clue is also deterministic.
    if (plan.actors or plan.genres or plan.language) and not plan.raw_terms:
        plan.route = "catalog_fast_path"
        return plan

    extracted = _llm_extract(query, catalog)
    if extracted is None:
        plan.llm_available = False
        plan.route = "lexical_fallback"
        return plan
    plan.llm_used = True
    plan.route = "llm_entity_extraction"
    # Restrict filters to names actually present in the query and the CMS catalog.
    # This prevents a hallucinated genre or query-language guess from filtering results.
    for genre in _as_strings(extracted.get("genres")):
        for known in known_genres:
            if normalized(genre) == normalized(known) and contains_phrase(clean, normalized(known)) and known not in plan.genres:
                plan.genres.append(known)
    for actor in _as_strings(extracted.get("actors")):
        for known in known_actors:
            if normalized(actor) == normalized(known) and contains_phrase(clean, normalized(known)) and known not in plan.actors:
                plan.actors.append(known)
    raw_set = set(plan.raw_terms)
    has_non_latin = any(ord(ch) > 127 and ch.isalpha() for ch in query)
    for phrase in _as_strings(extracted.get("scene_phrases")) + _as_strings(extracted.get("english_scene_keywords")):
        phrase = normalized(phrase).strip(" .,!?:;")
        words = [word for word in tokens(phrase) if word not in STOPWORDS]
        overlap = [word for word in words if word in raw_set]
        if not overlap and not has_non_latin:
            continue  # Reject story details the user never mentioned.
        if overlap and len(overlap) < len(words) and (len(words) > 2 or len(overlap) > 1):
            phrase = " ".join(overlap)  # Keep the grounded part only.
        if 2 <= len(phrase) <= 80 and phrase not in plan.scene_terms:
            plan.scene_terms.append(phrase)
    plan.scene_terms = plan.scene_terms[:8]
    return plan
