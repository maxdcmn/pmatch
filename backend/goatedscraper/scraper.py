from __future__ import annotations

"""
goatedscraper: Europe-scoped registry builder for ENG/PHYS/CS researchers.

- Enumerates EU/EEA/UK/CH institutions via OpenAlex
- Fetches authors by country + concept
- Pulls 5 most recent works, reconstructs abstracts
- Embeds abstracts (OpenAI), mean-pools to 1536-d vector
- Stores into Postgres (pgvector) across two tables: researchers, works

Run:
  export OPENAI_API_KEY=...
  export DATABASE_URL=postgresql://pmatch:pmatch@localhost:5432/pmatch
  python -m goatedscraper.scraper --country SE --concept cs --limit 100
"""

import argparse
import csv
import hashlib
import json
import os
import time
import random
from typing import Dict, Iterable, List, Optional
import logging

import httpx
import psycopg
from psycopg.rows import dict_row

import dotenv

dotenv.load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


CONCEPTS = {
    "cs": "C41008148",
    "physics": "C121332964",
    "engineering": "C127313418",
}

EU_COUNTRIES = {
    "AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IE","IT","LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE",
    "IS","LI","NO","CH","GB"
}


def openai_client():
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    try:
        return OpenAI(api_key=key)
    except Exception:
        return None


def mean_pool(vectors: List[List[float]]) -> Optional[List[float]]:
    if not vectors:
        return None
    dim = len(vectors[0])
    sums = [0.0] * dim
    for v in vectors:
        if len(v) != dim:
            return None
        for i, val in enumerate(v):
            sums[i] += float(val)
    n = float(len(vectors))
    return [s / n for s in sums]


def reconstruct(inv: Optional[Dict[str, List[int]]]) -> Optional[str]:
    if not inv:
        return None
    pairs = []
    for word, idxs in inv.items():
        for i in idxs:
            pairs.append((i, word))
    pairs.sort(key=lambda x: x[0])
    return " ".join(w for _, w in pairs)


def deterministic_id(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def get_conn() -> psycopg.Connection:
    dsn = os.getenv("DATABASE_URL", "postgresql://pmatch:pmatch@localhost:5432/pmatch")
    return psycopg.connect(dsn, row_factory=dict_row)


def upsert_researcher(cur, author: Dict, research_area: str, embedding: Optional[List[float]], email: Optional[str] = None):
    # Extract title from author data if available
    title = None
    if author.get("summary_stats", {}).get("h_index", 0) > 10:
        title = "Professor"  # High h-index suggests senior researcher
    elif author.get("summary_stats", {}).get("h_index", 0) > 5:
        title = "Associate Professor"
    else:
        title = "Researcher"
    
    cur.execute(
        """
        INSERT INTO researchers (id, name, email, institution, country, title, research_area, profile_url, embedding)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (id) DO UPDATE SET
          name=EXCLUDED.name,
          email=EXCLUDED.email,
          institution=EXCLUDED.institution,
          country=EXCLUDED.country,
          title=EXCLUDED.title,
          research_area=EXCLUDED.research_area,
          profile_url=EXCLUDED.profile_url,
          embedding=EXCLUDED.embedding,
          updated_at=NOW()
        """,
        (
            author["id"].split("/")[-1],
            author.get("display_name"),
            email,
            (author.get("last_known_institution") or {}).get("display_name"),
            (author.get("last_known_institution") or {}).get("country_code"),
            title,
            research_area,
            author.get("id"),
            embedding,
        ),
    )


def insert_work(cur, researcher_id: str, w: Dict):
    cur.execute(
        """
        INSERT INTO works (researcher_id, work_id, year, doi, url, abstract)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
        """,
        (
            researcher_id,
            w.get("id"),
            w.get("publication_year"),
            w.get("doi"),
            w.get("id"),
            reconstruct(w.get("abstract_inverted_index")),
        ),
    )


def _openalex_mailto() -> str:
    mail = os.getenv("OPENALEX_MAILTO") or os.getenv("OPENALEX_EMAIL") or os.getenv("CONTACT_EMAIL")
    if not mail:
        raise SystemExit("Set OPENALEX_MAILTO to your contact email (required by OpenAlex)")
    return mail


def openalex_get(url: str, params: Dict) -> Dict:
    mailto = _openalex_mailto()
    api_key = os.getenv("OPENALEX_API_KEY")
    app_ua = os.getenv("OPENALEX_USER_AGENT", "eu-research-scraper/1.0")
    headers = {
        "User-Agent": f"{app_ua} (mailto:{mailto})",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    # Always include mailto per OpenAlex guidelines
    params = {**params, "mailto": mailto}
    if api_key:
        params["api_key"] = api_key
    backoff = 1.0
    for attempt in range(8):
        with httpx.Client(timeout=httpx.Timeout(40), headers=headers, http2=True) as client:
            logging.debug("GET %s params=%s", url, params)
            r = client.get(url, params=params)
            if r.status_code in (429, 403, 502, 503):
                ra = r.headers.get("Retry-After")
                wait = float(ra) if ra and ra.isdigit() else backoff
                logging.warning("OpenAlex %s. Retrying in %.1fs (attempt %d)", r.status_code, wait, attempt + 1)
                time.sleep(wait)
                backoff = min(backoff * 2, 32)
                continue
            r.raise_for_status()
            return r.json()
    # final raise if all retries exhausted
    r.raise_for_status()


def list_authors(country: str, concept_id: str, per_page: int = 50) -> Iterable[Dict]:
    url = "https://api.openalex.org/authors"
    cursor = "*"
    while True:
        logging.info("Fetching authors: country=%s concept=%s cursor=%s", country, concept_id, cursor)
        data = openalex_get(
            url,
            params={
                # OpenAlex authors: use last_known_institutions (plural) and concepts.id
                "filter": f"last_known_institutions.country_code:{country},concepts.id:{concept_id}",
                "per_page": per_page,
                "cursor": cursor,
            },
        )
        for a in data.get("results", []):
            yield a
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(0.1 + random.random() * 0.2)  # jitter 100–300ms between pages


def list_works(author_openalex_id: str, per_page: int = 5) -> List[Dict]:
    url = "https://api.openalex.org/works"
    logging.debug("Fetching works for %s", author_openalex_id)
    data = openalex_get(url, params={"filter": f"author.id:{author_openalex_id}", "sort": "publication_date:desc", "per_page": per_page})
    return data.get("results", [])


def embed_texts(texts: List[str]) -> Optional[List[float]]:
    texts = [t for t in texts if t and t.strip()]
    if not texts:
        return None
    client = openai_client()
    if not client:
        return None
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts[:5])
    vecs = [d.embedding for d in resp.data]
    return mean_pool(vecs)


def tavily_client():
    try:
        from tavily import TavilyClient  # type: ignore
    except ImportError:
        return None
    key = os.getenv("TAVILY_API_KEY")
    print(key)
    if not key:
        return None
    return TavilyClient(api_key=key)


def search_researcher_email(name: str, institution: str) -> Optional[str]:
    """Search for researcher email using Tavily + LLM extraction."""
    client = tavily_client()
    if not client:
        logging.warning("No Tavily client available for email search")
        return None
    
    openai = openai_client()
    if not openai:
        logging.warning("No OpenAI client available for email extraction")
        return None
    
    try:
        # Search query combining name and institution
        query = f'"{name}" email contact {institution or ""}'.strip()
        logging.debug("Searching email for: %s", query)
        
        results = client.search(
            query=query,
            search_depth="basic",
            max_results=3,
            include_raw_content=True
        )
        
        # Combine raw content from search results
        content_parts = []
        for result in results.get("results", []):
            raw = result.get("raw_content", "")
            if raw and len(raw) > 50:
                content_parts.append(raw[:2000])  # Limit to avoid token limits
        
        if not content_parts:
            return None
            
        combined_content = "\n\n".join(content_parts)
        
        # Use LLM to extract email
        system_prompt = f"""You are extracting contact email addresses for researcher "{name}".
Look through the provided web content and find the most likely email address for this specific person.

Rules:
1. Return ONLY the email address, nothing else
2. If multiple emails found, return the most official/institutional one
3. If no email found, return "NONE"
4. Email must be valid format (contain @ and domain)
5. Prefer university/institution emails over personal ones"""

        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": combined_content[:8000]}  # Stay within token limits
            ],
            temperature=0.1,
            max_tokens=50
        )
        
        email = resp.choices[0].message.content.strip()
        if email and email != "NONE" and "@" in email and "." in email:
            logging.info("Found email for %s: %s", name, email)
            return email
        else:
            logging.debug("No valid email found for %s", name)
            return None
            
    except Exception as e:
        logging.warning("Email search failed for %s: %s", name, e)
        return None


def run(country: str, concept_key: str, limit: int | None, csv_out: Optional[str]) -> None:
    concept_id = CONCEPTS[concept_key]
    count = 0
    writer = None
    f = None
    if csv_out:
        # Match KTH scraper CSV format exactly
        fields = ["name", "email", "title", "research_area", "profile_url", "abstracts"]
        append = os.path.exists(csv_out)
        f = open(csv_out, "a" if append else "w", newline="", encoding="utf-8")
        writer = csv.DictWriter(f, fieldnames=fields, quoting=csv.QUOTE_ALL)
        if not append:
            writer.writeheader()
    
    with get_conn() as conn:
        with conn.cursor() as cur:
            for author in list_authors(country, concept_id):
                researcher_id = author["id"].split("/")[-1]
                works = list_works(author["id"]) or []
                abstracts = [reconstruct(w.get("abstract_inverted_index")) or "" for w in works]
                abstracts = [a for a in abstracts if a]  # Filter empty abstracts
                
                # Search for email using name + institution
                name = author.get("display_name", "")
                institution = (author.get("last_known_institution") or {}).get("display_name", "")
                email = search_researcher_email(name, institution) if name and institution else None
                
                # Generate title based on h-index
                title = "Researcher"  # Default
                h_index = author.get("summary_stats", {}).get("h_index", 0)
                if h_index > 10:
                    title = "Professor"
                elif h_index > 5:
                    title = "Associate Professor"
                
                emb = embed_texts(abstracts)
                upsert_researcher(cur, author, research_area=concept_key.title().replace("Cs", "Computer Science"), embedding=emb, email=email)
                
                for w in works:
                    insert_work(cur, researcher_id, w)
                
                if writer:
                    # Clean and format abstracts properly for CSV
                    clean_abstracts = []
                    for abstract in abstracts[:5]:
                        # Remove HTML entities and normalize whitespace
                        clean_abstract = abstract.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                        clean_abstract = " ".join(clean_abstract.split())  # Normalize whitespace
                        if len(clean_abstract) > 1000:  # Truncate very long abstracts
                            clean_abstract = clean_abstract[:1000] + "..."
                        clean_abstracts.append(clean_abstract)
                    
                    abstracts_text = "\n\n".join(clean_abstracts) if clean_abstracts else ""
                    
                    row = {
                        "name": " ".join(name.split()) if name else "",
                        "email": email or "",
                        "title": title or "",
                        "research_area": concept_key.title().replace("Cs", "Computer Science"),
                        "profile_url": author.get("id") or "",
                        "abstracts": abstracts_text,
                    }
                    writer.writerow(row)
                
                conn.commit()
                count += 1
                if count % 10 == 0:  # More frequent logging for email search
                    logging.info("Processed %d authors", count)
                if limit and count >= limit:
                    break
                    
                # Small delay to be respectful to Tavily API
                time.sleep(0.5)
    
    if f:
        f.close()
    logging.info("Done. Total authors processed: %d", count)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build EU researcher registry (OpenAlex -> Postgres)")
    parser.add_argument("--country", default="SE", help="Country code (e.g., SE, DE, FR)")
    parser.add_argument("--concept", dest="concept", choices=list(CONCEPTS.keys()), default="cs")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--csv", dest="csv_out", default=None, help="Optional CSV output path (like scraper CSV)")
    args = parser.parse_args()

    if args.country not in EU_COUNTRIES:
        raise SystemExit(f"Country {args.country} not in EU/EEA/UK/CH set")

    run(args.country, args.concept, limit=args.limit, csv_out=args.csv_out)
    print("Done.")


if __name__ == "__main__":
    main()


