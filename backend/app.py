from __future__ import annotations
from fastapi import FastAPI, APIRouter, HTTPException, status, UploadFile, File
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware
from typing import Optional, List
import uvicorn
import tempfile
import shutil
import logging
import sys
from pypdf import PdfReader

### pdf parsing
from user_info.paper_parsing import parse_paper_title_abstract as pp
from user_info.cv_parsing import generate_research_intro as gs

from utils.llm_manager import LLMManager
from db.pg_client import get_conn, upsert_user
import uuid
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('pmatch_api.log')
    ]
)
logger = logging.getLogger(__name__)

import dotenv
dotenv.load_dotenv()

app = FastAPI(title="PMatch API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=False,  # Set to False when allowing all origins
    allow_methods=["*"],
    allow_headers=["*"],
)


class LLMRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Message to send to the LLM")
    user_id: Optional[str] = Field(None, description="User ID to enable personalized matching")


class Contact(BaseModel):
    email: str
    name: str
    institution: Optional[str] = None
    country: Optional[str] = None
    title: Optional[str] = None
    research_area: Optional[str] = None
    profile_url: Optional[str] = None
    abstracts: Optional[List[str]] = None
    similarity_score: Optional[float] = None

class LLMResponse(BaseModel):
    message: str = Field(..., description="Your original message to the LLM")
    response: str = Field(..., description="LLM's response to your message")
    success: bool = True
    metadata: Optional[dict] = None
    contacts: Optional[List[Contact]] = Field(None, description="Extracted researcher contacts for email outreach")


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

class EmailGenerationRequest(BaseModel):
    user_id: str = Field(..., description="User ID to get CV context")
    contacts: List[Contact] = Field(..., description="List of researcher contacts to create generalized email for")
    email_type: str = Field("research_position_inquiry", description="Type of email to generate")

class EmailGenerationResponse(BaseModel):
    subject: str
    body: str
    personalization_notes: List[str] = Field(default_factory=list)
    success: bool = True


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
    logger.info(f"LLM Chat request: message='{request.message}', user_id={request.user_id}")
    try:
        from db.pg_client import get_user_by_id
        
        # Get user context if user_id provided
        user_context = None
        if request.user_id:
            logger.info(f"Looking up user context for user_id: {request.user_id}")
            user_data = get_user_by_id(request.user_id)
            if user_data:
                user_context = {
                    "user_id": user_data["id"],
                    "detected_kind": user_data["detected_kind"],
                    "title": user_data["title"],
                    "content": user_data["content"],
                    "filename": user_data["filename"],
                }
                logger.info(f"User context loaded: {user_data['detected_kind']} - {user_data['title']}")
            else:
                logger.warning(f"No user data found for user_id: {request.user_id}")

        llm_manager = LLMManager()
        logger.info("Calling LLM manager with tools...")
        llm_response = await llm_manager.chat_with_tools(request.message, user_context)
        
        logger.info(f"LLM response received: tools_used={llm_response.get('tools_used', [])}, "
                   f"tool_results_count={len(llm_response.get('tool_results', []))}")

        # Extract contacts from tool results
        contacts = []
        for i, tool_result in enumerate(llm_response.get("tool_results", [])):
            logger.info(f"Processing tool result {i}: {type(tool_result)}")
            logger.info(f"Tool result {i} keys: {list(tool_result.keys()) if isinstance(tool_result, dict) else 'Not a dict'}")
            logger.info(f"Tool result {i} content: {tool_result}")
            
            if isinstance(tool_result, dict) and "results" in tool_result:
                logger.info(f"Found {len(tool_result['results'])} results in tool result {i}")
                for j, result in enumerate(tool_result["results"]):
                    logger.info(f"Result {j} keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
                    logger.info(f"Result {j} email: {result.get('email') if isinstance(result, dict) else 'No email field'}")
                    if isinstance(result, dict) and result.get("email"):
                        logger.info(f"Creating contact {j}: {result.get('name')} - {result.get('email')}")
                        contacts.append(Contact(
                            email=result.get("email", ""),
                            name=result.get("name", ""),
                            institution=result.get("institution"),
                            country=result.get("country"),
                            title=result.get("title"),
                            research_area=result.get("research_area"),
                            profile_url=result.get("profile_url"),
                            abstracts=result.get("abstracts"),
                            similarity_score=result.get("similarity_score") or result.get("score")
                        ))
                    else:
                        logger.warning(f"Result {j} missing email or not a dict: {result}")
            else:
                logger.warning(f"Tool result {i} missing 'results' key or not a dict. Available keys: {list(tool_result.keys()) if isinstance(tool_result, dict) else 'Not a dict'}")

        logger.info(f"Returning response with {len(contacts)} contacts")
        return LLMResponse(
            message=request.message,
            response=llm_response["response"],
            success=True,
            metadata={
                "tools_used": llm_response.get("tools_used", []),
                "tool_results": llm_response.get("tool_results", []),
                "user_context_loaded": user_context is not None
            },
            contacts=contacts if contacts else None
        )

    except Exception as e:
        logger.error(f"LLM chat error: {str(e)}", exc_info=True)
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


@api.post("/generate-email", response_model=EmailGenerationResponse, summary="Generate personalized cold email")
async def generate_email(request: EmailGenerationRequest) -> EmailGenerationResponse:
    try:
        from db.pg_client import get_user_by_id
        from openai import OpenAI
        
        # Get user context
        user_data = get_user_by_id(request.user_id)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Prepare email generation prompt for multiple researchers
        client = OpenAI()
        
        # Aggregate researcher information
        institutions = list(set([c.institution for c in request.contacts if c.institution]))
        countries = list(set([c.country for c in request.contacts if c.country]))
        research_areas = list(set([c.research_area for c in request.contacts if c.research_area]))
        all_abstracts = []
        for contact in request.contacts:
            if contact.abstracts:
                all_abstracts.extend(contact.abstracts[:2])  # Take 2 abstracts per researcher
        
        researchers_summary = []
        for contact in request.contacts:
            researchers_summary.append(f"- {contact.name} ({contact.title or 'Researcher'}) at {contact.institution or 'University'}")
        
        system_prompt = f"""You are an expert at writing personalized academic cold emails for research collaboration inquiries.

Generate a professional, engaging cold email from a {user_data['detected_kind']} candidate to multiple researchers.

REQUIREMENTS:
- Professional but warm tone
- Reference the collective research areas and institutions represented
- Mention specific research themes from their combined work
- Clear research interest alignment with the group
- Specific mention of seeking research position/collaboration opportunities
- Include university/institution context for the region/area
- 250-350 words maximum
- Generate both subject and body
- Address it as a general inquiry to the research community

USER CONTEXT:
- Document type: {user_data['detected_kind']}
- Title: {user_data['title']}
- Content summary: {user_data['content'][:500]}...

RESEARCHERS GROUP CONTEXT:
- Number of researchers: {len(request.contacts)}
- Institutions: {', '.join(institutions)}
- Countries: {', '.join(countries)}
- Research areas: {', '.join(research_areas)}
- Researchers:
{chr(10).join(researchers_summary)}
- Sample research themes from their work: {all_abstracts[:5]}

Return JSON with:
- "subject": email subject line (should reflect multiple institutions/researchers)
- "body": email body content (address as general inquiry to research community)
- "personalization_notes": list of specific personalization elements used
"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Generate a cold email for research position inquiry to the research community at {', '.join(institutions[:3])} focusing on {', '.join(research_areas[:3])}."}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        return EmailGenerationResponse(
            subject=result.get("subject", "Research Collaboration Opportunity"),
            body=result.get("body", ""),
            personalization_notes=result.get("personalization_notes", []),
            success=True
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email generation failed: {str(e)}")


app.include_router(api)

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
