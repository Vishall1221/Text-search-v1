# Text Search v1 application

For macOS setup and transfer, see [`../mac_tutorial.md`](../mac_tutorial.md).

This is a deliberately small local implementation of the existing text-search flow. It reads only `cms` and `scene_embeddings`. Exact title/play queries bypass the LLM; simple known catalog filters can also bypass it. Other queries use the local Qwen model for field/scene-term extraction when available, then PostgreSQL shortlists lexical candidates and the hand-written phrase/word formula scores scenes. The final movie ordering uses **match score only**. There are no vector searches, numeric-score interpretations of LOW/MEDIUM/HIGH fields, performance or recency signals, campaigns, or conversation state.

## Layout

- `backend/`: API, query interpretation, SQL shortlist, lexical ranking, optional GCS video proxy.
- `frontend/`: minimal HTML/CSS/JS search page (no Node build).
- `../config/`: root-level `.env` and copyable `.env.example`. Environment variables override the file.
- `tests/`: unit checks for fast path, language handling, phrase scoring, and timestamps.

## Run on this PC

1. Start PostgreSQL using the command in `../Data-script/README.md` if it is stopped.
2. Start the local Qwen API using `../LLM-setup.md`. Search still works lexically if this server is off.
3. From the `Text-Search-v1` root, install API dependencies: `.\.venv\Scripts\python.exe -m pip install -r APP\requirements.txt`.
4. Run `.\.venv\Scripts\python.exe -m APP.start` (host/port come from root `config/.env`).
5. Open `http://127.0.0.1:8000`.

Health check: `http://127.0.0.1:8000/api/health`. Search API: `POST /api/search` with JSON `{"query":"Neel Shimana tea estate", "limit":8}`.

## Candidate and score rules

For a recognized title or cast/genre, candidate scenes come from matching CMS asset IDs. Other scene candidates match words/phrases in `scene_embeddings.search_text`, which contains description, master summary, visual summary, dialogue, events, and more. SQL returns at most 60 scenes per asset/language and 250 scenes overall. This is a shortlist, not vector similarity. Each scene gets the existing `0.70` base, `+0.22` phrase, up to `+0.20` high-value word, and up to `+0.08` thematic word adjustments, or `0.65` if unmatched. A movie receives the source's exact-title, cast, scene, or metadata match tier. Only `match_score` sorts the final movie list.

The old code sometimes describes this as a seven-tier system, but its active search function has six explicit branches, including the similar-title branch. This v1 retains the applicable exact-title, cast, scene, and metadata behavior; conversation-based similarity is excluded as agreed.

## Video playback

The browser cannot play a `gs://` URI directly. `Try video` calls the API, which reads the exact URI stored in CMS and attempts authenticated GCS byte-range streaming. The backend requires Google Application Default Credentials with access to the bucket. The provided JSON is fake, so its object paths may not exist. Search results and timestamps work regardless; playback then shows a clear 403, 404, or 503 message. No public URL is guessed and no credential is sent to the browser.
