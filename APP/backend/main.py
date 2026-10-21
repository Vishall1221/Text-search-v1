"""Local text-search API and small browser UI."""

from __future__ import annotations

from pathlib import Path

import psycopg
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from APP.backend.service import search_service
from APP.backend.video import video_response
from config.settings import settings


FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
app = FastAPI(title="Text Search v1", version="1.0.0")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=8, ge=1, le=20)


@app.get("/")
def home() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/health")
def health() -> dict[str, object]:
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2) as conn:
            movies, scenes = conn.execute(
                "SELECT (SELECT count(*) FROM cms), (SELECT count(*) FROM scene_embeddings)"
            ).fetchone()
        return {"status": "ok", "movies": movies, "scenes": scenes, "llm_configured": settings.llm_enabled}
    except psycopg.Error as exc:
        raise HTTPException(503, f"Database unavailable: {exc.__class__.__name__}") from exc


@app.post("/api/search")
def search(payload: SearchRequest) -> dict[str, object]:
    if not payload.query.strip():
        raise HTTPException(422, "Query cannot be blank")
    try:
        return search_service.search(payload.query.strip(), payload.limit)
    except psycopg.Error as exc:
        raise HTTPException(503, f"Database unavailable: {exc.__class__.__name__}") from exc


@app.get("/api/video/{asset_id}")
def video(asset_id: str, request: Request, language: str = Query(min_length=2)):
    try:
        return video_response(asset_id, language, request.headers.get("range"))
    except psycopg.Error as exc:
        raise HTTPException(503, f"Database unavailable: {exc.__class__.__name__}") from exc
