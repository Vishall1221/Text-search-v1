# Project-root configuration

Edit `.env` on this PC. Copy `.env.example` to `.env` on another machine. The API, importer, and verifier read this root configuration. Environment variables set by the shell take precedence. The database URL is password-free only because this local PostgreSQL cluster currently uses localhost `trust`; add a password and secure authentication before moving to a shared host or GCP.

`API_HOST`/`API_PORT` bind the app, `DATABASE_URL` connects the two source tables, `LLM_BASE_URL`/`LLM_MODEL` point to the locally running Qwen API, and the remaining values control timeouts, cache lifetime, and lexical candidate limits. Set `LLM_ENABLED=false` to run the deterministic and lexical baseline without invoking a model.

GCS playback uses Google Application Default Credentials, not a browser token. A local service-account file can be pointed to with `GOOGLE_APPLICATION_CREDENTIALS` in the process environment; the file itself should remain outside this project. Search does not require GCS credentials.
