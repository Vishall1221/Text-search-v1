-- Text-search v1 source tables. Embeddings are optional and are not generated
-- or searched by this version of the application.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS cms (
    asset_id TEXT NOT NULL,
    primary_language TEXT NOT NULL,
    title TEXT NOT NULL,
    movie_gcs_path TEXT NOT NULL,
    description TEXT,
    genres TEXT[] NOT NULL DEFAULT '{}',
    cast_names TEXT[] NOT NULL DEFAULT '{}',
    thumbnail_image_url TEXT,
    total_chunks INTEGER,
    total_scenes INTEGER NOT NULL,
    processed_at TIMESTAMPTZ,
    cms_metadata JSONB NOT NULL,
    source_metadata JSONB NOT NULL,
    source_file TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, primary_language),
    CHECK (asset_id <> '' AND primary_language <> '' AND title <> ''),
    CHECK (movie_gcs_path LIKE 'gs://%'),
    CHECK (total_scenes >= 0)
);

CREATE TABLE IF NOT EXISTS scene_embeddings (
    asset_id TEXT NOT NULL,
    primary_language TEXT NOT NULL,
    scene_id TEXT NOT NULL,
    scene_order INTEGER NOT NULL,
    chunk_id TEXT,
    start_time TEXT,
    end_time TEXT,
    start_seconds DOUBLE PRECISION NOT NULL,
    end_seconds DOUBLE PRECISION NOT NULL,
    duration_seconds DOUBLE PRECISION,
    description TEXT,
    master_scene_summary TEXT,
    visual_summary TEXT,
    dialogue_transcript TEXT,
    important_dialogue TEXT,
    mood TEXT,
    action_intensity TEXT,
    barc_retention_score TEXT,
    engaging_score TEXT,
    energy_level TEXT,
    cast_names TEXT[] NOT NULL DEFAULT '{}',
    entities_characters TEXT[] NOT NULL DEFAULT '{}',
    entities_objects TEXT[] NOT NULL DEFAULT '{}',
    tags TEXT[] NOT NULL DEFAULT '{}',
    search_text TEXT NOT NULL,
    scene_data JSONB NOT NULL,
    embedding vector,
    embedding_model TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, primary_language, scene_id),
    FOREIGN KEY (asset_id, primary_language)
        REFERENCES cms (asset_id, primary_language),
    CHECK (scene_order > 0 AND end_seconds > start_seconds)
);

CREATE INDEX IF NOT EXISTS cms_title_trgm_idx
    ON cms USING GIN (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS cms_genres_idx
    ON cms USING GIN (genres);
CREATE INDEX IF NOT EXISTS cms_cast_names_idx
    ON cms USING GIN (cast_names);
CREATE INDEX IF NOT EXISTS scene_embeddings_search_trgm_idx
    ON scene_embeddings USING GIN (search_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS scene_embeddings_time_idx
    ON scene_embeddings (asset_id, primary_language, start_seconds);
