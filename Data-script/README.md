# Text Search v1 data import

For the complete Mac setup, including when to skip ingestion into existing
tables, see [`../mac_tutorial.md`](../mac_tutorial.md).

The actual source folder on this PC is `C:\Users\jaira\Desktop\Datas\output` (10 movie JSON files), not `Datas\output json files`.

The importer creates only two application tables:

- `cms`: one row per asset/language pair, including the exact movie GCS URI, searchable CMS columns, complete `cms_metadata`, and every original top-level field in `source_metadata` (except the scene array).
- `scene_embeddings`: one row per scene, including searchable scene text and the complete original scene in `scene_data`. `embedding` and `embedding_model` are nullable placeholders; v1 does not generate or search vectors.

The importer validates every file before opening the database, performs the load in one transaction, and uses upserts so repeated runs do not duplicate rows. It never deletes rows. If scene content changes during a later import, any old embedding on that scene is cleared.

On this Windows PC, start the local database:

```powershell
& 'C:\Users\jaira\Desktop\AI-Search-DB\postgres\Library\bin\pg_ctl.exe' -D 'C:\Users\jaira\Desktop\AI-Search-DB\data' -l 'C:\Users\jaira\Desktop\AI-Search-DB\server.log' -o '-h 127.0.0.1 -p 5432' start
```

Validate, ingest, and independently compare stored JSON to the source:

```powershell
& 'C:\Users\jaira\Desktop\Text-Search-v1\.venv\Scripts\python.exe' 'C:\Users\jaira\Desktop\Text-Search-v1\Data-script\ingest.py' --source 'C:\Users\jaira\Desktop\Datas\output' --dry-run
& 'C:\Users\jaira\Desktop\Text-Search-v1\.venv\Scripts\python.exe' 'C:\Users\jaira\Desktop\Text-Search-v1\Data-script\ingest.py' --source 'C:\Users\jaira\Desktop\Datas\output'
& 'C:\Users\jaira\Desktop\Text-Search-v1\.venv\Scripts\python.exe' 'C:\Users\jaira\Desktop\Text-Search-v1\Data-script\verify.py' --source 'C:\Users\jaira\Desktop\Datas\output'
```

For another machine, create a Python environment and install `requirements.txt`. Copy the project-root `config/.env.example` to `config/.env` and set the Mac's `DATABASE_URL` there. The importer and verifier both read that root configuration; `--dsn` or a shell `DATABASE_URL` can override it. Pass the real JSON folder with `--source`. PostgreSQL and pgvector must be installed on that machine before ingesting. The Windows test database accepts password-free connections only on `127.0.0.1`; configure authentication before exposing or sharing it.
