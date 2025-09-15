# PMatch - Research Collaboration Platform

AI-powered platform for finding and connecting with research collaborators using semantic matching of CVs, papers, and research interests.

## Quick Start

### Prerequisites
- Python 3.9+
- Node.js 18+
- Docker & Docker Compose
- OpenAI API key

### Setup

```bash
# Clone and setup
git clone <repo-url>
cd pmatch

# Backend setup
cd backend
cp .env.example .env  # Add your OPENAI_API_KEY
pip install -r requirements.txt

# Start database
docker-compose up -d

# Run backend
python app.py

# Frontend setup (new terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

## Architecture

### Backend (FastAPI)
- **API Server**: FastAPI with CORS for frontend integration
- **Document Processing**: PDF parsing for CVs (short docs) vs papers (long docs)
- **Vector Search**: OpenAI embeddings with PostgreSQL+pgvector
- **LLM Integration**: GPT-4o for chat, matching, and email generation
- **Web Scraping**: Automated researcher data collection

### Frontend (Next.js)
- **UI Framework**: React 19 + Next.js 15 with shadcn/ui components
- **Styling**: Tailwind CSS with dark/light theme support
- **Components**: Modern workspace interface with chat and file upload

### Database (PostgreSQL + pgvector)

#### Tables

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

## API Endpoints

### Document Upload
**`POST /api/upload-pdf`**
- Uploads CV or research paper
- Auto-detects document type (CV: ≤5 pages, Paper: >5 pages)
- Generates embeddings for similarity matching
- Returns `user_id` for subsequent operations

### AI Chat & Matching
**`POST /api/llm-chat`**
- Natural language interface for researcher discovery
- Supports uploaded document context via `user_id`
- Returns matching researchers with contact information
- Available tools:
  - `find_matches_for_user`: Personalized matching based on uploaded CV/paper
  - `get_top_matches`: General search by research keywords
  - `list_institutions`: Show available institutions

### Vector Search
**`POST /api/search`**
- Direct vector similarity search
- Returns ranked researcher profiles
- Configurable result count (1-20)

### Email Generation
**`POST /api/generate-email`**
- Creates personalized outreach emails
- Uses uploaded document context and researcher profiles
- Generates subject lines and collaboration-focused content

## Key Components

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
**Location**: `backend/scraper/`
- **Target**: KTH researcher directory
- **Data Collected**:
  - Basic info: name, email, title, research area
  - Publication abstracts (up to 3 per researcher)
  - Institution and country information
- **Process**:
  1. Scrapes main directory page
  2. Visits individual researcher profiles
  3. Extracts publication links and abstracts
  4. Generates embeddings for similarity search
- **Output**: CSV format ready for database import

## Development

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
python db/upload_to_pg.py
```
Note: scraper/ subdir currently unused

### Frontend Development
```bash
cd frontend

# Install dependencies
npm install

# Development server
npm run dev

# Build for production
npm run build
```

## Environment Variables

### Backend (.env)
```bash
OPENAI_API_KEY=your_openai_api_key
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=pmatch
POSTGRES_USER=pmatch
POSTGRES_PASSWORD=pmatch
```

### Frontend
Configuration handled through Next.js environment system.

## Data Flow

1. **Upload**: User uploads CV/paper → Document processing → Embedding generation → Database storage
2. **Search**: User query → Embedding generation → Vector similarity search → Ranked results
3. **Chat**: Natural language → LLM tool selection → Database queries → Formatted response
4. **Email**: Selected researchers + user context → LLM generation → Personalized outreach email

## Vector Search Details

- **Model**: OpenAI text-embedding-3-small (1536 dimensions)
- **Index**: PostgreSQL pgvector with IVFFlat index
- **Distance**: Cosine similarity for semantic matching
- **Performance**: Optimized for real-time queries with 100-list IVFFlat index

## Deployment

### Production Setup
1. **Database**: PostgreSQL with pgvector extension
2. **Backend**: FastAPI server with Uvicorn
3. **Frontend**: Next.js build with static export
4. **Environment**: Set all required environment variables
5. **Scaling**: Consider vector index tuning for larger datasets

### Docker Deployment
```bash
# Database only
docker-compose up -d

# Full stack deployment (extend docker-compose.yml)
# Add backend and frontend services as needed
```

## Testing

### Backend Tests
```bash
cd backend
pytest
```

### API Testing
Use the included test files or tools like Postman to test endpoints with sample data.

## Performance Considerations

- **Vector Search**: IVFFlat index with 100 lists optimized for ~1K-10K profiles
- **Embedding Cache**: Consider caching frequently accessed embeddings
- **Rate Limits**: OpenAI API rate limiting for embedding generation
- **Database**: Regular VACUUM and ANALYZE for vector index maintenance

## Contributing

1. Fork the repository
2. Create feature branch
3. Follow existing code style
4. Add tests for new functionality
5. Submit pull request

*PMatch - Connecting researchers through AI-powered semantic matching*