"""
LLM manager: minimal, concise interface for HTML-to-abstract extraction.

Environment:
- OPENAI_API_KEY (optional). If missing, functions return empty results.
"""

from __future__ import annotations

import os
from typing import List
import logging
import dotenv

dotenv.load_dotenv()

SYSTEM_PROMPT = (
    "You are an information extraction agent. Given raw HTML or visible text of a "
    "publication page or publications list, extract concise English abstracts. "
    "Return a JSON array of strings (each string is one abstract). If no abstracts "
    "exist, return an empty JSON array. Keep each abstract under 1200 characters."
)

LINK_SELECTOR_PROMPT = (
    "You are a link selector. You will receive a list of candidate links from a "
    "researcher profile page as 'TEXT | URL' lines plus some page text. "
    "Return a JSON array of URLs that are most likely to lead to a publications "
    "list or publication entries. Prefer links containing words like "
    "'Publikationslista', 'Publications', 'Google Scholar', 'Research outputs'."
)


def _has_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def extract_abstracts_with_llm(html_or_text: str, model: str = "gpt-4o-mini") -> List[str]:
    if not _has_key() or not html_or_text or len(html_or_text) < 40:
        return []
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI()
        content = html_or_text if len(html_or_text) <= 100_000 else html_or_text[:100_000]
        logging.info("LLM extract: sending %d chars", len(content))
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            temperature=0,
        )
        text = resp.choices[0].message.content or "[]"
        # Very defensive JSON parsing
        import json

        arr = json.loads(text) if text.strip().startswith("[") else []
        abstracts = [str(x)[:1200] for x in arr if isinstance(x, str)]
        logging.info("LLM extract: got %d abstracts", len(abstracts))
        return abstracts
    except Exception as e:
        logging.exception("LLM extract failed: %s", e)
        return []


def choose_publication_links(candidate_lines: List[str], page_text: str, model: str = "gpt-4o-mini") -> List[str]:
    if not _has_key() or not candidate_lines:
        return []
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI()
        lines = "\n".join(candidate_lines)
        content = f"Candidates:\n{lines}\n\nPage Text (truncated):\n{page_text[:4000]}\n\nReturn JSON array of URLs only."
        logging.info("LLM link select: %d candidates", len(candidate_lines))
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": LINK_SELECTOR_PROMPT},
                {"role": "user", "content": content},
            ],
            temperature=0,
        )
        import json

        text = resp.choices[0].message.content or "[]"
        urls = json.loads(text) if text.strip().startswith("[") else []
        urls = [u for u in urls if isinstance(u, str) and u.startswith("http")]
        logging.info("LLM link select: chose %d urls", len(urls))
        return urls
    except Exception as e:
        logging.exception("LLM link select failed: %s", e)
        return []


