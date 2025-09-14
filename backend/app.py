from __future__ import annotations
from fastapi import FastAPI, APIRouter, HTTPException, status, UploadFile, File
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
from typing import Optional, List
import uvicorn
import tempfile
import shutil
from pypdf import PdfReader

### pdf parsing
from user_info.paper_parsing import parse_paper_title_abstract as pp
from user_info.cv_parsing import generate_research_intro as gs

from utils.llm_manager import LLMManager
from db.pg_client import get_conn, upsert_user
import uuid

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


class LLMRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Message to send to the LLM")
    user_id: Optional[str] = Field(None, description="User ID to enable personalized matching")


class LLMResponse(BaseModel):
    message: str = Field(..., description="Your original message to the LLM")
    response: str = Field(..., description="LLM's response to your message")
    success: bool = True
    metadata: Optional[dict] = None


class UploadResponse(BaseModel):
    filename: str
    content_type: str
    message: str
    detected_kind: Optional[str] = None
    result: Optional[dict] = None
    embedding: Optional[List[float]] = None
    user_id: str


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
    # Validate content type
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a PDF")

    # Generate unique user ID
    user_id = str(uuid.uuid4())

    # Save upload to temporary PDF
    await file.seek(0)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf_path = tmp.name
        shutil.copyfileobj(file.file, tmp)

    # Count pages and decide parsing path
    try:
        n_pages = len(PdfReader(pdf_path).pages)
    except Exception:
        n_pages = 0
    detected = "paper" if n_pages > 5 else "cv"

    try:
        if detected == "paper":
            # Use paper parser: returns { title, abstract }
            parsed = pp(pdf_path)
            title = (parsed or {}).get("title", "")
            abstract = (parsed or {}).get("abstract", "")
            combined = f"\n\n".join([title, abstract]).strip()

            # Embed with our embed-query helper
            embedding = _embed_query(combined)

            # Store user data in database
            upsert_user(
                id=user_id,
                filename=file.filename or "unknown.pdf",
                content_type=file.content_type or "application/pdf",
                detected_kind=detected,
                title=title,
                content=combined,
                embedding=embedding,
            )

            # Write combined text to a temp file for legacy compatibility
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as tf:
                tf.write(combined)
                txt_path = tf.name

            return UploadResponse(
                filename=file.filename,
                content_type=file.content_type,
                message="Parsed paper successfully",
                detected_kind=detected,
                result={
                    "title": title,
                    "abstract": abstract,
                    "combined_text_file": txt_path,
                    "pages": n_pages,
                },
                embedding=embedding,
                user_id=user_id,
            )
        else:
            # CV path: parse to text, then generate a ~5-sentence intro
            from user_info.cv_parsing import parse_pdf_with_openai as pcv  # local import to avoid circularity
            cv_text = pcv(pdf_path)
            intro = gs(cv_text)

            embedding = _embed_query(intro)

            # Store user data in database
            upsert_user(
                id=user_id,
                filename=file.filename or "unknown.pdf",
                content_type=file.content_type or "application/pdf",
                detected_kind=detected,
                title=file.filename or "CV",  # Use filename as title for CV
                content=intro,
                embedding=embedding,
            )

            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8") as tf:
                tf.write(intro)
                intro_path = tf.name

            return UploadResponse(
                filename=file.filename,
                content_type=file.content_type,
                message="Parsed CV successfully",
                detected_kind=detected,
                result={
                    "intro": intro,
                    "intro_text_file": intro_path,
                    "pages": n_pages,
                },
                embedding=embedding,
                user_id=user_id,
            )
    finally:
        # Cleanup uploaded temp PDF (keep generated .txt for audit if needed)
        try:
            import os
            os.unlink(pdf_path)
        except Exception:
            pass


@api.post("/llm-chat", response_model=LLMResponse, summary="Chat with LLM")
async def llm_chat(request: LLMRequest) -> LLMResponse:
    try:
        from db.pg_client import get_user_by_id
        
        # Get user context if user_id provided
        user_context = None
        if request.user_id:
            user_data = get_user_by_id(request.user_id)
            if user_data:
                user_context = {
                    "user_id": user_data["id"],
                    "detected_kind": user_data["detected_kind"],
                    "title": user_data["title"],
                    "content": user_data["content"],
                    "filename": user_data["filename"],
                }

        llm_manager = LLMManager()
        llm_response = await llm_manager.chat_with_tools(request.message, user_context)

        return LLMResponse(
            message=request.message,
            response=llm_response["response"],
            success=True,
            metadata={
                "tools_used": llm_response.get("tools_used", []),
                "tool_results": llm_response.get("tool_results", []),
                "user_context_loaded": user_context is not None
            }
        )

    except Exception as e:
        return LLMResponse(
            message=request.message,
            response=f"Error: {str(e)}",
            success=False
        )


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
