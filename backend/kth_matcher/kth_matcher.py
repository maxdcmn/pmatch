"""
KTH professor similarity matcher using OpenAI Deep Research + embeddings.

Functions for use from a Jupyter notebook:

  - configure_logging(): optional console logging
  - match_kth_professors(
        cv_pdf_path: str,
        our_abstracts: list[str],
        output_csv: str = "kth_professor_matches.csv",
        top_k: int = 5,
        dr_model: str = "o3-deep-research",
        embed_model: str = "text-embedding-3-large",
        allowed_domains: tuple[str, ...] = ("kth.se", "people.kth.se", "kth.diva-portal.org"),
    ) -> str | None

Notes:
 - Requires: openai, pypdf, numpy
   Install in notebook: %pip install -q openai pypdf numpy
 - Deep Research browsing must be enabled on your key for dr_model; otherwise
   the function logs a warning and returns None.
 - This uses web_search_preview tool, instructing it to return structured JSON
   of professors and their publications. The JSON is then embedded and scored.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence, Tuple

import numpy as np

try:
    from openai import OpenAI  # type: ignore
    from openai import APITimeoutError  # type: ignore
except Exception:
    OpenAI = None  # type: ignore
    class APITimeoutError(Exception):  # type: ignore
        pass

try:
    import httpx  # type: ignore
except Exception:
    httpx = None  # type: ignore

try:
    from pypdf import PdfReader  # type: ignore
except Exception:
    PdfReader = None  # type: ignore


logger = logging.getLogger("kth.matcher")


def configure_logging(level: int = logging.INFO) -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.getLogger().setLevel(level)


def _load_openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_AI_KEY")
    if not key and os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    m = re.match(r"\s*OPEN_AI_KEY\s*=\s*(.+)", line)
                    if m:
                        key = m.group(1).strip().strip('"').strip("'")
                        break
        except Exception as e:
            logger.debug("Failed reading .env: %s", e)
    if not key:
        raise RuntimeError("OPEN_AI_KEY not found in environment or .env")
    os.environ["OPENAI_API_KEY"] = key
    return key


def _extract_text_from_pdf(path: str) -> str:
    if PdfReader is None:
        raise RuntimeError("pypdf not installed. Run: pip install pypdf")
    reader = PdfReader(path)
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n".join(p.strip() for p in parts if p)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _chunk(text: str, max_chars: int = 4000) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    i = 0
    while i < len(text):
        j = min(len(text), i + max_chars)
        # try to cut on sentence boundary
        k = text.rfind(".", i, j)
        if k == -1 or k - i < max_chars * 0.5:
            k = j
        else:
            k += 1
        chunks.append(text[i:k].strip())
        i = k
    return [c for c in chunks if c]


def _embed_texts(client: Any, texts: Sequence[str], model: str) -> np.ndarray:
    if not texts:
        return np.zeros((0, 1536), dtype=np.float32)
    # Call embeddings in batches to reduce overhead
    vecs: list[list[float]] = []
    for t in texts:
        resp = client.embeddings.create(model=model, input=t)
        vecs.append(resp.data[0].embedding)
    return np.array(vecs, dtype=np.float32)


def _average(vectors: np.ndarray) -> np.ndarray:
    if vectors.size == 0:
        return np.zeros((vectors.shape[1] if vectors.ndim == 2 else 1536,), dtype=np.float32)
    v = vectors.astype(np.float32)
    v = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-8)
    return np.mean(v, axis=0)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) + 1e-8) * (np.linalg.norm(b) + 1e-8)
    return float(np.dot(a, b) / denom)


@dataclass
class Professor:
    name: str
    email: str
    profile_url: str
    publications: list[dict]  # each: {"title": str, "abstract": str}


def _extract_text_from_response_obj(resp) -> Optional[str]:
    text = getattr(resp, "output_text", None)
    if text:
        return text.strip()
    try:
        parts = getattr(resp, "output", None)
        if isinstance(parts, list) and parts:
            buf = []
            for item in parts:
                content = getattr(item, "content", None)
                if isinstance(content, list):
                    for c in content:
                        t = getattr(c, "text", None)
                        if t:
                            buf.append(t)
            if buf:
                return "\n".join(buf).strip()
    except Exception:
        pass
    return None


def _wait_for_background(client: Any, rid: str, timeout_s: int, poll_s: float, partial_after_s: Optional[int] = None) -> tuple[str, str]:
    deadline = time.time() + timeout_s
    start = time.time()
    last_status = None
    last_log = 0.0
    while True:
        try:
            resp = client.responses.retrieve(rid)
        except APITimeoutError:
            logger.warning("Polling timed out for job %s; retrying until overall timeout.", rid)
            if time.time() > deadline:
                raise
            time.sleep(max(1.0, poll_s))
            continue
        except Exception as e:
            if httpx is not None and isinstance(e, (httpx.ReadTimeout, httpx.ConnectTimeout)):  # type: ignore[attr-defined]
                logger.warning("HTTP timeout during polling job %s; retrying.", rid)
                if time.time() > deadline:
                    raise
                time.sleep(max(1.0, poll_s))
                continue
            logger.warning("Transient polling error for job %s: %s", rid, e)
            if time.time() > deadline:
                raise
            time.sleep(max(1.0, poll_s))
            continue

        status = getattr(resp, "status", None)
        if status != last_status:
            logger.debug("responses.get(%s) -> status=%s", rid, status)
            last_status = status
        now = time.time()
        if now - last_log > 30:
            logger.info("Deep research job %s status=%s", rid, status)
            last_log = now
        # If caller allows partial results and enough time has passed, return best-effort text
        if partial_after_s is not None and (time.time() - start) >= partial_after_s:
            text = _extract_text_from_response_obj(resp)
            if text:
                return text, "partial"
        if status in ("completed", "failed", "cancelled", "expired"):
            break
        if time.time() > deadline:
            raise TimeoutError(f"Responses job {rid} did not finish within {timeout_s}s")
        time.sleep(poll_s)

    if status != "completed":
        raise RuntimeError(f"Responses job {rid} ended with status={status}")
    text = _extract_text_from_response_obj(resp)
    if not text:
        raise RuntimeError("Empty response text from Responses API (background)")
    return text, "completed"


def _responses_collect_professors(
    client: Any,
    dr_model: str,
    allowed_domains: Sequence[str],
    min_expected: int = 20,
    max_professors: int = 20,
    background_timeout_s: int = 1800,
    background_poll_s: float = 2.0,
    partial_after_s: Optional[int] = None,
) -> list[Professor] | None:
    """Use o3-deep-research to return a JSON list of professors with publications.

    Returns None and logs a warning if browsing is not available.
    """
    allowed = ", ".join(sorted(set(allowed_domains)))
    instructions = f"""
You are a research agent with web browsing enabled.
Rules:
- Search ONLY these domains: {allowed}
- Target: KTH professors (Royal Institute of Technology, Stockholm) whose research involves machine learning or AI.
- For each professor, include their official KTH profile URL and email (if public).
- Collect several publications per professor with title and abstract text; prefer KTH pages (or KTH DiVA portal) where abstracts are present.
- Return ONLY a compact JSON array (no markdown) of objects with keys: name, email, profile_url, publications (list of {{title, abstract}}).
- Aim to return up to {max_professors} professor objects; do not exceed {max_professors}.
If browsing tools are NOT available, reply exactly with NO_BROWSING_AVAILABLE and nothing else.
""".strip()

    try:
        resp = client.responses.create(
            model=dr_model,
            instructions=instructions,
            input="Collect KTH ML/AI professors with publications and abstracts as specified.",
            tools=[{"type": "web_search_preview"}],
            tool_choice="auto",
            background=True,
        )
    except Exception as e:
        logger.error("OpenAI Responses API error: %s", e)
        raise

    rid = getattr(resp, "id", None)
    if not rid:
        raise RuntimeError("Missing response id for background job")
    text, status = _wait_for_background(
        client,
        rid,
        timeout_s=background_timeout_s,
        poll_s=background_poll_s,
        partial_after_s=partial_after_s,
    )

    text = text.strip()
    if text == "NO_BROWSING_AVAILABLE":
        logger.warning("Deep Research browsing not available on your key/model. Returning None.")
        return None

    # Remove optional code fences
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n```$", "", text).strip()

    def parse_professors_from_text(txt: str) -> list[dict]:
        # First, try strict JSON array
        try:
            raw = json.loads(txt)
            return raw if isinstance(raw, list) else []
        except Exception:
            pass

        # Next, try NDJSON (one JSON object per line)
        items: list[dict] = []
        for line in txt.splitlines():
            s = line.strip().rstrip(',')
            if not s or not (s.startswith('{') and (s.endswith('}') or s.endswith('},'))):
                continue
            try:
                obj = json.loads(s.rstrip(','))
                if isinstance(obj, dict):
                    items.append(obj)
            except Exception:
                continue
        if items:
            return items

        # Finally, try to extract top-level JSON objects from a (possibly partial) array
        objs: list[str] = []
        depth = 0
        buf = []
        in_obj = False
        for ch in txt:
            if ch == '{':
                depth += 1
                in_obj = True
            if in_obj:
                buf.append(ch)
            if ch == '}':
                depth -= 1
                if depth == 0 and in_obj:
                    objs.append(''.join(buf))
                    buf = []
                    in_obj = False
        items2: list[dict] = []
        for s in objs:
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    items2.append(obj)
            except Exception:
                continue
        return items2

    raw_items = parse_professors_from_text(text) if text else []
    if not raw_items:
        if status == "partial":
            logger.warning("No parseable partial results yet; returning None early.")
            return None
        logger.error("Failed to parse JSON from model output (no items).")
        raise ValueError("Failed to parse JSON from model output")

    profs: list[Professor] = []
    for item in raw_items[:max_professors]:
        try:
            name = str(item.get("name", "")).strip()
            email = str(item.get("email", "")).strip()
            prof_url = str(item.get("profile_url", "")).strip()
            pubs = item.get("publications", []) or []
            clean_pubs: list[dict] = []
            for p in pubs:
                t = str(p.get("title", "")).strip()
                a = str(p.get("abstract", "")).strip()
                if t or a:
                    clean_pubs.append({"title": t, "abstract": a})
            if name and prof_url:
                profs.append(Professor(name=name, email=email, profile_url=prof_url, publications=clean_pubs))
        except Exception:
            continue
    return profs


def match_kth_professors(
    cv_pdf_path: str,
    our_abstracts: Sequence[str],
    output_csv: str = "kth_professor_matches.csv",
    top_k: int = 5,
    dr_model: str = "o3-deep-research",
    embed_model: str = "text-embedding-3-large",
    allowed_domains: Sequence[str] = ("kth.se", "people.kth.se", "kth.diva-portal.org"),
    background_timeout_s: int = 1800,
    background_poll_s: float = 2.0,
    client_timeout_s: int = 120,
    client_max_retries: int = 2,
    early_return_s: Optional[int] = None,
    max_professors: int = 20,
    max_pubs_per_prof: int = 5,
) -> Optional[str]:
    """
    End-to-end: parse CV, embed our profile+abstracts, use Deep Research to fetch
    KTH professors+publications, embed and compute similarity, and write top-K CSV.

    CSV columns: name,email,profile_url,score,top_publication,top_abstract
    Returns output path on success, or None if browsing isn't available.
    """
    if OpenAI is None:
        raise RuntimeError("openai package not installed. Run: pip install openai")
    if PdfReader is None:
        raise RuntimeError("pypdf package not installed. Run: pip install pypdf")

    _load_openai_key()
    client = OpenAI(timeout=client_timeout_s, max_retries=client_max_retries)

    # 1) Build our profile text
    cv_text = _extract_text_from_pdf(cv_pdf_path)
    abstracts_text = "\n\n".join([a.strip() for a in our_abstracts if a and a.strip()])
    our_text = (cv_text + "\n\n" + abstracts_text).strip()
    our_chunks = _chunk(our_text, max_chars=4000)
    our_vecs = _embed_texts(client, our_chunks, embed_model)
    our_vec = _average(our_vecs)

    # 2) Deep Research: get candidate professors and publications
    profs = _responses_collect_professors(
        client,
        dr_model,
        allowed_domains,
        min_expected=20,
        max_professors=max_professors,
        background_timeout_s=background_timeout_s,
        background_poll_s=background_poll_s,
        partial_after_s=early_return_s,
    )
    if profs is None:
        # Browsing unavailable
        return None
    if not profs:
        logger.warning("Deep Research returned no professors.")
        return None

    # 3) Embed publications and score similarity
    results: list[tuple[Professor, float, str, str]] = []  # (prof, score, top_pub_title, top_pub_abstract)
    for prof in profs:
        # Keep titles aligned with abstracts after filtering so indices match
        filtered = [(p.get("title", "").strip(), p.get("abstract", "").strip()) for p in prof.publications if p.get("abstract")]
        if not filtered:
            continue
        # Limit per professor to keep calls reasonable
        filtered = filtered[:max_pubs_per_prof]
        pub_titles = [t for (t, _) in filtered]
        pub_abstracts = [a for (_, a) in filtered]
        pub_vecs = _embed_texts(client, pub_abstracts, embed_model)
        if pub_vecs.size == 0:
            continue
        # Compute cosine with each abstract; take best
        best_idx = -1
        best_score = -1.0
        for i in range(pub_vecs.shape[0]):
            score = _cosine(our_vec, pub_vecs[i])
            if score > best_score:
                best_score = score
                best_idx = i
        top_title = pub_titles[best_idx] if best_idx >= 0 and best_idx < len(pub_titles) else ""
        top_abstract = pub_abstracts[best_idx] if best_idx >= 0 and best_idx < len(pub_abstracts) else ""
        # Assert we actually have an abstract for the chosen top publication
        if not top_abstract:
            logger.warning("Skipping %s because no abstract was available for the top publication.", prof.name)
            continue
        # Log a short preview of the abstract for verification
        preview = (top_abstract[:200] + ("…" if len(top_abstract) > 200 else "")).replace("\n", " ")
        logger.info("Top abstract for %s: %s", prof.name, preview)
        results.append((prof, float(best_score), top_title, top_abstract))

    # 4) Rank and keep top K
    results.sort(key=lambda x: x[1], reverse=True)
    top = results[:top_k]
    if not top:
        logger.warning("No comparable publications found to score.")
        return None

    # 5) Write CSV (include the matched top publication abstract for traceability)
    import csv
    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "email", "profile_url", "score", "top_publication", "top_abstract"])
        for prof, score, top_title, top_abstract in top:
            writer.writerow([prof.name, prof.email, prof.profile_url, f"{score:.4f}", top_title, top_abstract])

    logger.info("Wrote top-%d matches to %s", len(top), output_csv)
    return output_csv


__all__ = [
    "configure_logging",
    "match_kth_professors",
]
