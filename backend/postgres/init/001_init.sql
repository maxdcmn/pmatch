CREATE EXTENSION IF NOT EXISTS vector;

-- Table to store KTH profiles and abstracts with averaged embedding
CREATE TABLE IF NOT EXISTS profiles (
  id TEXT PRIMARY KEY,
  name TEXT,
  email TEXT,
  title TEXT,
  research_area TEXT,
  profile_url TEXT UNIQUE,
  abstracts TEXT[],           -- list of abstracts
  embedding vector(1536),      -- mean of embeddings (text-embedding-3-small)
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Vector index for fast similarity search
CREATE INDEX IF NOT EXISTS profiles_embedding_ivfflat
  ON profiles USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_profiles_updated ON profiles;
CREATE TRIGGER trg_profiles_updated
BEFORE UPDATE ON profiles
FOR EACH ROW EXECUTE FUNCTION set_updated_at();


