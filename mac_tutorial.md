# Run Text Search v1 on a Mac

This guide is for the **Text-Search-v1** project. Run commands from the project
root (the folder containing `APP`, `Data-script`, `config`, and `models`). The
Mac runs the same search code; only local software, credentials, and paths need
Mac-specific setup. The app reads two PostgreSQL tables: `cms` and
`scene_embeddings`. It does **not** use vector search in v1.

## 1. Transfer the code through GitHub

On Windows, push the **code and instructions** to a GitHub repository. Include
`APP/`, `Data-script/`, the root `config/` template and Python settings,
`.gitignore`, `LLM-setup.md`, and this `mac_tutorial.md`. A private repository
is appropriate if the code or metadata belongs to your company. Before the
push, review the staged-file list: do not upload real movie JSON, database
files, credentials, or service-account keys.

The project's `.gitignore` excludes these machine-specific or large items:

| Do not push | Why |
| --- | --- |
| `models/` | The Qwen `.gguf` is about 2.5 GB; download it separately on Mac |
| `runtime/`, `downloads/` | Windows/CUDA binaries and ZIPs cannot run on Mac |
| `.venv/`, `__pycache__/` | Install Python dependencies anew on Mac |
| `config/.env` | Local settings; may contain database credentials |

`config/.env.example` **is** safe to push; it is only a template. Seeing
`config/.env` in your editor does not mean Git will upload it. Git ignore
controls staging, not file visibility. If `.env` was committed *before* the
ignore rule existed, remove it from Git tracking and rotate any exposed
credentials before pushing.

For the **empty Text-search-v1 GitHub repository**, these PowerShell commands
on Windows stage only the project source and documentation. Inspect
`git status --short` before committing:

```powershell
cd 'C:\Users\jaira\Desktop\Text-Search-v1'
git init
git add .gitignore APP Data-script config/.env.example config/README.md config/__init__.py config/settings.py LLM-setup.md mac_tutorial.md
git status --short
git commit -m "Add text search v1 code and Mac setup guide"
git branch -M main
git remote add origin https://github.com/Vishall1221/Text-search-v1.git
git push -u origin main
```

Do not continue past `git status --short` if it shows model files, raw movie
JSON, credentials, or any file you do not intend to publish. If this folder is
already a Git repository or already has an `origin`, reuse that setup instead
of repeating `git init` or `git remote add origin`.

On the Mac, clone that GitHub repository and enter its root:

```bash
git clone "https://github.com/Vishall1221/Text-search-v1.git"
cd Text-search-v1
```

The cloned project will **not yet contain the Qwen model**; step 5 downloads
the exact file.
Keep your real movie JSON files in their existing Mac folder; do not add them
to this code repository.

## 2. Connect to PostgreSQL already on the Mac

**If your real data is already in PostgreSQL, do not reinstall PostgreSQL or
re-ingest it.** Confirm that the existing database has the *expected columns*,
not merely tables with the same names. Compare its `cms` and
`scene_embeddings` definitions with `Data-script/schema.sql`. To inspect it,
connect with your Mac's PostgreSQL client and run:

```sql
SELECT count(*) FROM cms;
SELECT count(*) FROM scene_embeddings;
```

In `psql`, `\d cms` and `\d scene_embeddings` show the columns. If the tables
were created with this project's `schema.sql`, the app should be able to use
them. If they were created differently, **stop before importing**: the app's
SQL may need adapting. The importer uses upserts, so re-running it on the same
`asset_id` + language would update existing rows; it does not delete older
rows.

If there is **no database yet**, install PostgreSQL and pgvector, create a
database and login on the Mac, then use step 4 to import your JSON. For a
Homebrew-managed PostgreSQL 17 installation, the packages and service commands
are:

```bash
brew install postgresql@17 pgvector
brew services start postgresql@17
```

Use pgvector built for the **same PostgreSQL major version** as your server.
The fresh-import schema creates the `vector` and `pg_trgm` extensions even
though the v1 search does not query embeddings. These packages are not a
replacement for creating a PostgreSQL database and login.

## 3. Configure this Mac

The single config folder is at the project root: `config/`. If `config/.env`
does not exist, copy the template:

```bash
cp config/.env.example config/.env
```

Edit `config/.env` and set `DATABASE_URL` to **this Mac's** database host,
username, password, port, and database name. For example (replace every
placeholder, including the password):

```text
DATABASE_URL=postgresql://MAC_USER:MAC_PASSWORD@127.0.0.1:5432/MAC_DATABASE
LLM_BASE_URL=http://127.0.0.1:8081
LLM_ENABLED=true
```

If the password contains URL-special characters such as `@`, `:`, `/`, or `#`,
percent-encode them in `DATABASE_URL`. Do not share or commit `config/.env`;
it is Git-ignored. Shell environment variables override `.env`. Both the app
and the importer read this root config. No Python source-code edit is needed
just to change the database connection.

## 4. Create a Mac Python environment; import only if needed

Use Python 3.11 or newer. Do not reuse the Windows `.venv`:

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r APP/requirements.txt -r Data-script/requirements.txt
```

If the Mac database **already has your real data in the matching two tables**,
skip the following import commands. If it is a **new, empty database**, first
validate your real JSON without writing anything, then import and verify:

```bash
python Data-script/ingest.py --source "/path/to/your/real/json/folder" --dry-run
python Data-script/ingest.py --source "/path/to/your/real/json/folder"
python Data-script/verify.py --source "/path/to/your/real/json/folder"
```

The importer expects one movie object per `.json` file, with `asset_id`,
`title`, `primary_language`, a `gs://` `movie_gcs_path`, `cms_metadata`, and
`scenes`. `total_scenes` must equal the length of `scenes`. A dry-run failure
means the real JSON format needs review before ingesting.

## 5. Download and run Qwen on the Mac

From the project root, create `models/` and download the **exact same Qwen
quantization** used on Windows. The official file is hosted at the
[Unsloth Hugging Face model repository](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/blob/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf):

```bash
mkdir -p models
curl -fL --retry 3 --output models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
shasum -a 256 models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf
```

The expected SHA-256 is
`3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597`.
If the downloaded file's checksum differs, do not run it; retry the download.
This is a roughly 2.5 GB download. If you already copied this exact `.gguf`
file to the Mac by USB or another transfer, put it at this path instead of
downloading again.

The Windows `runtime` is not portable. Install a macOS llama.cpp runtime
(Homebrew example):

```bash
brew install llama.cpp
```

From the project root, start its server in **Terminal window 1** and leave
that window open:

```bash
llama-server -m models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf -c 2048 -ngl 99 --host 127.0.0.1 --port 8081
```

This loads the model file in `models/`; it does not download it again. If you want to
check database/search wiring *before* starting Qwen, set `LLM_ENABLED=false`
in `config/.env` temporarily. Searches still run with deterministic and
lexical fallback, but complex queries will not get Qwen extraction.

## 6. Run the app

Open **Terminal window 2**, change to the project root, activate the Mac
environment, and run:

```bash
cd "/path/to/Text-Search-v1"
source .venv/bin/activate
python -m APP.start
```

Open <http://127.0.0.1:8000> in your browser. The health endpoint is
<http://127.0.0.1:8000/api/health>. Terminal window 1 must remain running for
Qwen-assisted queries; Terminal window 2 must remain running for the app.
PostgreSQL must also be running. Stop either foreground server with Ctrl+C.

## Video playback (optional)

Search and timestamps do not require Google Cloud credentials. To play a
private `gs://` movie, the Mac running the API also needs Google Application
Default Credentials with permission to read the object. Keep credential files
outside the project and do not send them to the browser or commit them.

## What changes on the Mac?

| Item | Mac action |
| --- | --- |
| Python search code | No code changes expected; run from the project root |
| `config/.env` | Use the Mac PostgreSQL connection and local Qwen URL |
| Python environment | Create a new Mac `.venv` and install requirements |
| Qwen model `.gguf` | Download separately after cloning, or copy this exact file by USB |
| Qwen runtime | Install macOS llama.cpp; Windows `.exe` files cannot run |
| PostgreSQL tables | Reuse matching existing tables, or create/import once |
| Real movie JSON | Keep on Mac; provide its path only for a fresh import |
| GCS credentials | Only needed for private movie playback |

Official installation references: [PostgreSQL 17 Homebrew formula](https://formulae.brew.sh/formula/postgresql%4017),
[pgvector installation](https://github.com/pgvector/pgvector#homebrew),
[llama.cpp Homebrew formula](https://formulae.brew.sh/formula/llama.cpp), and
[llama-server usage](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).
