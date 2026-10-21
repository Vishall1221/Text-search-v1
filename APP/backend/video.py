"""Best-effort authenticated, byte-range GCS proxy for local browser playback."""

from __future__ import annotations

import re

import psycopg
from fastapi import HTTPException, Response
from google.api_core.exceptions import Forbidden, NotFound
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import storage

from config.settings import settings


MAX_CHUNK = 4 * 1024 * 1024


def video_response(asset_id: str, language: str, range_header: str | None) -> Response:
    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute(
            "SELECT movie_gcs_path FROM cms WHERE asset_id = %s AND primary_language = %s",
            (asset_id, language.upper()),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Movie not found in CMS")
    uri = row[0]
    match = re.fullmatch(r"gs://([^/]+)/(.+)", uri)
    if not match:
        raise HTTPException(422, "Stored GCS URI is invalid")
    bucket, object_name = match.groups()

    try:
        blob = storage.Client().bucket(bucket).blob(object_name)
        blob.reload()
        size = blob.size or 0
        if size <= 0:
            raise HTTPException(404, "Video object is empty")
        start = 0
        end = min(size - 1, MAX_CHUNK - 1)
        if range_header:
            requested = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not requested:
                raise HTTPException(416, "Unsupported byte range")
            first, last = requested.groups()
            if not first and not last:
                raise HTTPException(416, "Unsupported byte range")
            if first:
                start = int(first)
                if start >= size:
                    raise HTTPException(416, "Byte range outside video")
                if last and int(last) < start:
                    raise HTTPException(416, "Invalid byte range")
                end = min(size - 1, start + MAX_CHUNK - 1, int(last) if last else size - 1)
            else:
                suffix = min(int(last), MAX_CHUNK, size)
                if suffix <= 0:
                    raise HTTPException(416, "Unsupported byte range")
                start, end = size - suffix, size - 1
        data = blob.download_as_bytes(start=start, end=end)
        return Response(
            content=data,
            status_code=206,
            media_type="video/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Content-Length": str(len(data)),
                "Cache-Control": "private, max-age=60",
            },
        )
    except DefaultCredentialsError as exc:
        raise HTTPException(503, "GCS credentials are not configured on this PC") from exc
    except NotFound as exc:
        raise HTTPException(404, "GCS video object does not exist") from exc
    except Forbidden as exc:
        raise HTTPException(403, "GCS credentials cannot read this video") from exc
