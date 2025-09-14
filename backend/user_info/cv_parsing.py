from __future__ import annotations

"""
OpenAI-powered PDF parsing utility.

This module uploads a PDF to OpenAI and asks a multimodal model to extract
structured text from it. It returns the extracted text as a single string.

Requirements:
- OPENAI_API_KEY in environment (backend/.env supported)
- openai>=1.51.0

Usage:
- From code: parse_pdf_with_openai("/path/to/file.pdf") -> str
- CLI/dev: python backend/user_info/cv_parsing.py
"""

from typing import Optional
import os
import pathlib

from dotenv import load_dotenv
from openai import OpenAI


def _get_client() -> OpenAI:
    # Load env from backend/.env if present
    here = pathlib.Path(__file__).resolve()
    env_path = here.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()  # fallback to default search
    return OpenAI()


def parse_pdf_with_openai(
    pdf_path: str,
    *,
    model: str = "gpt-4o-mini",  # multimodal + cost-effective
    instructions: Optional[str] = None,
) -> str:
    """Parse a PDF using OpenAI's Responses API with file input.

    - Uploads the PDF
    - Asks the model to extract readable text with headings and bullet points
    - Returns the extracted text as a single string
    """

    path = pathlib.Path(pdf_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    client = _get_client()

    # Upload the PDF for use with the Responses API
    with path.open("rb") as f:
        uploaded = client.files.create(file=f, purpose="assistants")

    prompt = instructions or (
        "You are a precise CV parser. Extract the full readable text from the "
        "attached PDF preserving section headings, lists, dates, and employer/education "
        "entities where possible. Keep the original order. Return plain UTF-8 text."
    )

    # Compose a multimodal input that references the uploaded file
    resp = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_file", "file_id": uploaded.id},
                ],
            }
        ],
    )

    # Extract plain text output
    # responses API: resp.output_text aggregates all text outputs
    text = getattr(resp, "output_text", None)
    if not text:
        # Fallback: walk content if needed
        try:
            chunks = []
            for item in getattr(resp, "output", []) or []:
                if item.get("type") == "message":
                    for ct in item.get("content", []) or []:
                        if ct.get("type") == "output_text":
                            chunks.append(ct.get("text", ""))
                        elif ct.get("type") == "output_image":
                            # ignore images for this use case
                            pass
            text = "\n".join(chunks).strip()
        except Exception:
            text = ""

    return text or ""


if __name__ == "__main__":
    # Simple smoke test: parse backend/CV.pdf
    default_pdf = pathlib.Path(__file__).resolve().parent.parent / "CV.pdf"
    target = os.environ.get("CV_PATH", str(default_pdf))
    print(f"[cv_parsing] Parsing PDF: {target}")
    try:
        out = parse_pdf_with_openai(target)
        print("[cv_parsing] Extracted text preview (first 800 chars):\n")
        print(out[:8000])
        if len(out) > 8000:
            print("\n[cv_parsing] ... (truncated)")
    except Exception as e:
        print(f"[cv_parsing] Error: {e}")

