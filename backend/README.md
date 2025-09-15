# PMatch Backend

### Prerequisites
- Python 3.11+
- Docker
- API keys

### FastAPI Backend
- **API Server**: FastAPI with CORS for frontend integration
- **Document Processing**: PDF parsing for CVs (short docs) vs papers (long docs)
- **Vector Search**: OpenAI embeddings with PostgreSQL+pgvector
- **LLM Integration**: GPT-4o for chat, matching, and email generation
- **Web Scraping**: Automated researcher data collection


### Database tables

**`profiles`** - Researcher data
```sql
id TEXT PRIMARY KEY,
name TEXT,
email TEXT,
institution TEXT,
country TEXT,
title TEXT,
research_area TEXT,
profile_url TEXT UNIQUE,
abstracts TEXT[],           -- Research paper abstracts
embedding vector(1536),     -- Averaged embeddings for similarity search
created_at TIMESTAMP,
updated_at TIMESTAMP
```

**`users`** - Uploaded documents
```sql
id TEXT PRIMARY KEY,
filename TEXT,
content_type TEXT,
detected_kind TEXT,         -- 'cv' or 'paper'
title TEXT,                 -- Document title
content TEXT,               -- Processed text content
embedding vector(1536),     -- Document embedding
created_at TIMESTAMP,
updated_at TIMESTAMP
```

### API Endpoints

**`POST /api/upload-pdf`** - Document Upload
- Uploads CV or research paper
- Auto-detects document type (CV: ≤5 pages, Paper: >5 pages)
- Generates embeddings for similarity matching
- Returns `user_id` for subsequent operations

**`POST /api/llm-chat`** - AI Chat & Matching
- Natural language interface for researcher discovery
- Supports uploaded document context via `user_id`
- Returns matching researchers with contact information
- Available tools:
  - `find_matches_for_user`: Personalized matching based on uploaded CV/paper
  - `get_top_matches`: General search by research keywords
  - `list_institutions`: Show available institutions

**`POST /api/search`** - Vector Search
- Direct vector similarity search
- Returns ranked researcher profiles
- Configurable result count (1-20)

**`POST /api/generate-email`** - Email Generation
- Creates personalized outreach emails
- Uses uploaded document context and researcher profiles
- Generates subject lines and collaboration-focused content


### Document Processing Pipeline
1. **PDF Upload**: Validates and temporarily stores uploaded files
2. **Type Detection**: Page count determines CV vs paper processing
3. **Content Extraction**:
   - **CVs**: Full text extraction → AI-generated research summary
   - **Papers**: Title and abstract extraction
4. **Embedding Generation**: OpenAI text-embedding-3-small (1536 dimensions)
5. **Database Storage**: Processed content with vector embeddings

### Research Matching System
- **Semantic Search**: Vector similarity using pgvector with cosine distance
- **Personalized Matching**: User document embeddings vs researcher profiles
- **Keyword Search**: Natural language queries converted to embeddings
- **Institution Filtering**: Optional filtering by research institution

### Web Scraper
- **Target**: KTH researcher directory
- **Data Collected**:
  - Basic info: name, email, title, research area
  - Publication abstracts (up to 3 per researcher)
  - Institution and country information
- **Process**:
  1. Gets data from OpenAlex API
  2. Visits individual researcher profiles and finds their institution emails with Tavely.
  3. Extracts publication links and abstracts
  4. Generates embeddings for similarity search
- **Output**: CSV format ready for database import

### Environment Variables
```bash
OPENAI_API_KEY=your_openai_api_key
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=pmatch
POSTGRES_USER=pmatch
POSTGRES_PASSWORD=pmatch
```

### Database Management
```bash
# Start PostgreSQL with pgvector
docker-compose up -d

# Connect to database
docker exec -it pmatch_pg psql -U pmatch -d pmatch # this might be done by the docker compose idk

# Run migrations
psql -U pmatch -d pmatch -f postgres/init/001_init.sql
```

### Backend Development
```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run with auto-reload
python app.py

# Run scraper
python goatedscraper/scraper.py

# Upsert to database
python db/upload_to_pg.py # This may take a while, we're not infra devs
```

### Performance Considerations

- **Vector Search**: IVFFlat index with 100 lists optimized for ~1K-10K profiles
- **Embedding Cache**: Consider caching frequently accessed embeddings
- **Rate Limits**: OpenAI API rate limiting for embedding generation
