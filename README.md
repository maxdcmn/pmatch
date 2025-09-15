# pmatch : finding your next PhD or Thesis contact with AI
![License](https://img.shields.io/github/license/maxdcmn/pmatch)
![Status](https://img.shields.io/badge/status-WIP-green )

![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)

Applications for both jobs and research positions are becoming more and more crowded by the day as students eagerly apply to every possible opening they can find. It's easy to apply via an open position on linkedin or a university website, but you'll often find **far more success reaching out to professors and researchers**. You'll often learn more about research at that university and faculty in particular and your chances of landing a position are much greater.

---

### Backend & Data Engineering
- **Database**: PostgreSQL with pgvector extension for semantic search
- **Document Processing**: Auto-detects CV vs Research Papers (≤5 pages vs >5 pages)
- **Vector Embeddings**: OpenAI text-embedding-3-small (1536 dimensions)
- **Search Performance**: IVFFlat index optimized for real-time similarity queries
- **Web Scraping**: Automated researcher profile collection from university directories
- **Similarity Matching**: Cosine distance-based semantic researcher matching
- **API**: FastAPI with async processing for document upload and matching
- **Email Generation**: GPT-4o powered personalized outreach messages

---

## Contributors
- [maxdcmn](https://github.com/maxdcmn)
- [NikVis01](https://github.com/NikVis01)
- [ltumat](https://github.com/ltumat)
