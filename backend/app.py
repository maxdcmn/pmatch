from __future__ import annotations
from fastapi import FastAPI, APIRouter, HTTPException, status, UploadFile, File
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
from typing import Optional, List
import uvicorn


app = FastAPI(title="PMatch API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost",
        "http://127.0.0.1",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ItemCreate(BaseModel):
    """Request model for creating an item (placeholder)."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)


class ItemRead(BaseModel):
    """Response model for an item (placeholder)."""

    id: int
    name: str
    description: str | None = None


class LLMRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Message to send to the LLM")


class LLMResponse(BaseModel):
    message: str = Field(..., description="Your original message to the LLM")
    response: str = Field(..., description="LLM's response to your message")
    success: bool = True
    data: Optional[dict] = None


class UploadResponse(BaseModel):
    filename: str
    content_type: str
    message: str


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)


class ProfileHit(BaseModel):
    id: str
    name: str
    email: str
    title: str | None = None
    research_area: str | None = None
    profile_url: str | None = None
    abstracts: List[str] | None = None
    score: float


api = APIRouter(prefix="/api", tags=["api"])

@app.get("/healthz", tags=["health"], summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@api.post("/upload-pdf", response_model=UploadResponse, summary="Upload PDF file")
async def upload_pdf(file: UploadFile = File(...)) -> UploadResponse:
    
    if not file.content_type == "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a PDF"
        )

    await file.seek(0)
    
    return UploadResponse(
        filename=file.filename,
        content_type=file.content_type,
        message="PDF uploaded successfully"
    )


@api.post("/llm-chat", response_model=LLMResponse, summary="Chat with LLM")
def llm_chat(request: LLMRequest) -> LLMResponse:
    llm_response = "This is a placeholder."
    
    return LLMResponse(
        message=request.message,
        response=llm_response,
        success=True,
        data={"contact": {
            "text": "Dear Mr. Doe, I'm Max. I'm reaching out to you because I'm interested in your work.",
            "email": "max@pmatch.com",
            "subject": "Collaboration proposal",
            }
        }
    )


# ---- Retrieval over Postgres (pgvector) ----

def _embed_query(text: str) -> List[float]:
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        raise HTTPException(status_code=500, detail="OpenAI client not installed")
    client = OpenAI()
    resp = client.embeddings.create(model="text-embedding-3-small", input=[text])
    return resp.data[0].embedding  # type: ignore


@api.post("/search", response_model=list[ProfileHit], summary="Vector search profiles")
def search_profiles_api(payload: SearchRequest) -> list[ProfileHit]:
    from db.pg_client import search_profiles  # local import to keep startup lean
    embedding = _embed_query(payload.query)
    try:
        rows = search_profiles(embedding, top_k=payload.top_k)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")
    hits: list[ProfileHit] = []
    for r in rows:
        hits.append(ProfileHit(
            id=str(r.get("id")),
            name=r.get("name"),
            email=r.get("email"),
            title=r.get("title"),
            research_area=r.get("research_area"),
            profile_url=r.get("profile_url"),
            abstracts=r.get("abstracts"),
            score=float(r.get("score", 0.0)),
        ))
    return hits


app.include_router(api)

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
