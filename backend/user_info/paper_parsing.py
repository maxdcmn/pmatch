from __future__ import annotations

"""
Paper parsing helper using OpenAI's multimodal Responses API.

Functionality:
- Takes a PDF path, trims to the first `max_pages` (default 5), uploads to OpenAI,
  and asks the model to return only the paper title and abstract.
- Returns a dict with keys: {"title": str, "abstract": str}.

Env/Deps:
- OPENAI_API_KEY must be set (backend/.env is loaded if present)
- openai>=1.51.0, python-dotenv, pypdf
"""

from typing import Optional, Dict
import io
import json
import os
import pathlib
import tempfile

from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader, PdfWriter


def _load_env() -> None:
    here = pathlib.Path(__file__).resolve()
    env_path = here.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()


def _get_client() -> OpenAI:
    _load_env()
    return OpenAI()


def _trim_pdf_first_pages(src_path: pathlib.Path, max_pages: int) -> pathlib.Path:
    reader = PdfReader(str(src_path))
    writer = PdfWriter()
    pages = min(len(reader.pages), max_pages)
    for i in range(pages):
        writer.add_page(reader.pages[i])

    tmp = tempfile.NamedTemporaryFile(prefix="paper_first_pages_", suffix=".pdf", delete=False)
    tmp_path = pathlib.Path(tmp.name)
    with tmp:
        writer.write(tmp)
    return tmp_path

def _extract_text_first_pages(src_path: pathlib.Path, max_pages: int) -> str:
    reader = PdfReader(str(src_path))
    pages = min(len(reader.pages), max_pages)
    parts: list[str] = []
    for i in range(pages):
        try:
            txt = reader.pages[i].extract_text() or ""
            if txt:
                parts.append(txt)
        except Exception:
            pass
    return "\n\n".join(p.strip() for p in parts if p)


def _cap_text_prioritizing_abstract(
    text: str,
    *,
    cap: int = 120_000,
    pre_window: int = 2_000,
    post_window: int = 8_000,
) -> str:
    """Trim text to `cap` chars but try to keep an abstract snippet in view.

    - Looks for keywords like 'Abstract', 'Sammanfattning', or 'Summary'.
    - If found beyond the cap, include a window around it and prepend the head.
    - If not found, returns the head slice.
    """
    if len(text) <= cap:
        return text

    low = text.lower()
    idx = None
    for pat in (r"\babstract\b", r"\bsammanfattning\b", r"\bsummary\b"):
        m = re.search(pat, low)
        if m:
            idx = m.start()
            break

    if idx is None:
        return text[:cap]

    # Build an abstract-focused window
    s = max(0, idx - pre_window)
    e = min(len(text), idx + post_window)
    chunk = text[s:e]

    if len(chunk) >= cap:
        return chunk[:cap]

    sep = "\n\n--- abstract (ensured) ---\n\n"
    head_budget = cap - len(chunk) - len(sep)
    head = text[:max(0, head_budget)]
    return head + sep + chunk


def parse_paper_title_abstract(
    pdf_path: str,
    *,
    model: str = "gpt-4o-mini",
    max_pages: int = 5,
    system_prompt: Optional[str] = None,
) -> Dict[str, str]:
    """Parse a paper PDF and extract only title and abstract from first pages.

    Returns: {"title": str, "abstract": str}
    """

    src = pathlib.Path(pdf_path)
    if not src.exists() or not src.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    client = _get_client()
    # Extract text locally from the first `max_pages` to avoid empty responses
    text_first_pages = _extract_text_first_pages(src, max_pages)
    # Safety cap, but ensure we keep the abstract in view if present
    text_first_pages = _cap_text_prioritizing_abstract(text_first_pages, cap=120_000)

    sys_text = system_prompt or (
        "You are an expert paper parser. Given the raw text from the first few pages of a PDF, "
        "extract only the 'title' and 'abstract'. If a field is missing, return an empty string for it."
    )

    comp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": sys_text},
            {
                "role": "user",
                "content": (
                    'Return strictly this JSON: {"title": string, "abstract": string}.\n\n'
                    'Text from first pages (up to 5):\n' + text_first_pages
                ),
            },
        ],
        temperature=0,
    )

    result_text = (comp.choices[0].message.content or "{}").strip()
    data: Dict[str, str] = {"title": "", "abstract": ""}
    try:
        obj = json.loads(result_text)
        if isinstance(obj, dict):
            data["title"] = str(obj.get("title", "") or "").strip()
            data["abstract"] = str(obj.get("abstract", "") or "").strip()
            return data
    except Exception:
        pass

    # Fallback heuristics if JSON parsing failed
    lines = [ln.strip() for ln in text_first_pages.splitlines() if ln.strip()]
    if lines and not data["title"]:
        data["title"] = lines[0]
    low = text_first_pages.lower()
    i = low.find("abstract")
    if i != -1 and not data["abstract"]:
        after = text_first_pages[i: i + 2000]
        # crude: take text after the word 'abstract'
        data["abstract"] = after.split("\n\n", 1)[-1].strip()
    return data


if __name__ == "__main__":
    # If PAPER_PATH is set, test only that file. Otherwise, try two defaults
    # in the backend/ folder: ba_thesis.pdf and adam.pdf
    env_pdf = os.environ.get("PAPER_PATH")
    if env_pdf:
        if not pathlib.Path(env_pdf).exists():
            print(f"[paper_parsing] Test file not found: {env_pdf}")
        else:
            print(f"[paper_parsing] Parsing first pages of: {env_pdf}")
            out = parse_paper_title_abstract(env_pdf)
            print("[paper_parsing] Result:\n", json.dumps(out, ensure_ascii=False, indent=2))
    else:
        root = pathlib.Path(__file__).resolve().parent.parent
        candidates = [root / "ba_thesis.pdf", root / "adam.pdf"]
        any_found = False
        for p in candidates:
            if p.exists():
                any_found = True
                print(f"[paper_parsing] Parsing first pages of: {p}")
                out = parse_paper_title_abstract(str(p))
                print("[paper_parsing] Result:\n", json.dumps(out, ensure_ascii=False, indent=2))
                print()
        if not any_found:
            print("[paper_parsing] No default test PDFs found (backend/ba_thesis.pdf, backend/adam.pdf). "
                  "Set PAPER_PATH to a PDF path to test.")
