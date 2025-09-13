-- Goated scraper schema (researchers + works)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS researchers (
  id TEXT PRIMARY KEY,
  name TEXT,
  email TEXT,
  institution TEXT,
  country TEXT,
  title TEXT,
  research_area TEXT,
  profile_url TEXT UNIQUE,
  embedding vector(1536),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS works (
  researcher_id TEXT REFERENCES researchers(id) ON DELETE CASCADE,
  work_id TEXT,
  year INT,
  doi TEXT,
  url TEXT,
  abstract TEXT,
  PRIMARY KEY (researcher_id, work_id)
);

-- indexes
CREATE INDEX IF NOT EXISTS idx_researchers_country ON researchers(country);
CREATE INDEX IF NOT EXISTS idx_researchers_area ON researchers(research_area);
-- hnsw is fast for recall; requires pgvector >= 0.5
CREATE INDEX IF NOT EXISTS idx_researchers_embedding_hnsw
  ON researchers USING hnsw (embedding vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_works_by_year ON works(researcher_id, year DESC);

-- updated_at trigger
CREATE OR REPLACE FUNCTION set_updated_at_researchers()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_researchers_updated ON researchers;
CREATE TRIGGER trg_researchers_updated
BEFORE UPDATE ON researchers
FOR EACH ROW EXECUTE FUNCTION set_updated_at_researchers();


