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
    if not key:
        logging.debug("No TAVILY_API_KEY found")
        return None
    try:
        client = TavilyClient(api_key=key)
        # Test the client with a simple search to verify it works
        client.search("test", max_results=1)
        logging.debug("Tavily client test successful")
        return client
    except Exception as e:
        logging.debug("Tavily client test failed: %s", e)
        return None


def generate_likely_emails(name: str, institution: str) -> List[str]:
    """Generate likely email patterns for a researcher."""
    if not name:
        return []
    
    name_parts = name.split()
    first_name = name_parts[0].lower() if name_parts else ""
    last_name = name_parts[-1].lower() if len(name_parts) > 1 else ""
    
    # Common Swedish institutional domains (prioritized)
    domains = []
    if institution:
        inst_lower = institution.lower()
        if "kth" in inst_lower or "royal institute" in inst_lower:
            domains.extend(["kth.se"])
        elif "stockholm" in inst_lower:
            domains.extend(["su.se", "ki.se"])
        elif "chalmers" in inst_lower:
            domains.extend(["chalmers.se"])
        elif "lund" in inst_lower:
            domains.extend(["lu.se"])
        elif "uppsala" in inst_lower:
            domains.extend(["uu.se"])
        elif "gothenburg" in inst_lower or "göteborg" in inst_lower:
            domains.extend(["gu.se"])
    
    # Default Swedish universities for researchers in Sweden
    if not domains:
        domains.extend(["kth.se", "su.se", "lu.se", "uu.se", "chalmers.se"])
    
    # Add some generic domains as backup
    domains.extend(["gmail.com", "outlook.com"])
    
    # Generate email patterns
    emails = []
    for domain in domains:
        if first_name and last_name:
            emails.extend([
                f"{first_name}.{last_name}@{domain}",
                f"{first_name}{last_name}@{domain}",
                f"{first_name[0]}{last_name}@{domain}",
                f"{last_name}@{domain}",
            ])
        elif first_name:
            emails.append(f"{first_name}@{domain}")
    
    return emails[:10]  # Limit to top 10 candidates


def search_researcher_email(name: str, institution: str) -> Optional[str]:
    """Search for researcher email using multiple strategies."""
    client = tavily_client()
    if not client:
        logging.info("No Tavily client available - generating likely email patterns for %s", name)
        # Fallback: generate likely emails (for demonstration)
        likely_emails = generate_likely_emails(name, institution)
        if likely_emails:
            logging.info("Generated likely emails for %s: %s", name, likely_emails[:3])
            return likely_emails[0]  # Return most likely one
        else:
            logging.warning("No likely emails generated for %s (institution: %s)", name, institution)
        return None
    
    openai = openai_client()
    if not openai:
        logging.warning("No OpenAI client available for email extraction")
        return None
    
    try:
        # Extract first and last name for targeted search
        name_parts = name.split()
        first_name = name_parts[0].lower() if name_parts else ""
        last_name = name_parts[-1].lower() if len(name_parts) > 1 else ""
        
        # Multiple search strategies
        search_queries = [
            f'"{name}" email contact {institution or ""}',
            f'{first_name}.{last_name}@',
            f'{first_name}@{institution or "university"}',
            f'"{name}" professor email',
            f'"{name}" researcher contact information',
        ]
        
        all_content = []
        
        for query in search_queries:
            logging.debug("Searching email with query: %s", query)
            try:
                results = client.search(
                    query=query.strip(),
                    search_depth="advanced",  # Increased depth
                    max_results=5,  # More results
                    include_raw_content=True
                )
                
                for result in results.get("results", []):
                    raw = result.get("raw_content", "")
                    if raw and len(raw) > 30:
                        all_content.append(raw[:1500])
                        
            except Exception as e:
                logging.debug("Search query failed: %s - %s", query, e)
                continue
        
        if not all_content:
            return None
            
        combined_content = "\n\n".join(all_content)
        
        # Enhanced LLM prompt for email extraction
        system_prompt = f"""Extract the email address for researcher "{name}" from the text below.

SEARCH PATTERNS:
- Look for {first_name}.{last_name}@domain.com
- Look for {first_name}@domain.com  
- Look for {last_name}@domain.com
- Look for any email containing "{first_name}" or "{last_name}"

RULES:
1. Return ONLY the email address, nothing else
2. Must be a valid email format (contains @ and domain)
3. Prefer university/institutional emails (.edu, .ac.uk, .se, etc.)
4. If multiple emails found, return the most official one
5. If no email found, return "NONE"

RESEARCHER: {name}
INSTITUTION: {institution or "Unknown"}"""

        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": combined_content[:10000]}  # More content
            ],
            temperature=0.0,  # More deterministic
            max_tokens=100
        )
        
        email = resp.choices[0].message.content.strip()
        
        # Validate email format and relevance
        if email and email != "NONE" and "@" in email and "." in email:
            # Check if email contains researcher's name components
            email_lower = email.lower()
            if (first_name in email_lower or last_name in email_lower or 
                any(part.lower() in email_lower for part in name_parts if len(part) > 2)):
                logging.info("Found email for %s: %s", name, email)
                return email
        
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
        # Match KTH scraper CSV format + add institution and country
        fields = ["name", "email", "title", "institution", "country", "research_area", "profile_url", "abstracts"]
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
                
                # Extract institution info from affiliations or last_known_institution
                name = author.get("display_name", "")
                institution = ""
                country = ""
                
                # Try last_known_institution first
                if author.get("last_known_institution"):
                    institution = author["last_known_institution"].get("display_name", "")
                    country = author["last_known_institution"].get("country_code", "")
                
                # If no last_known_institution, get most recent Swedish affiliation
                if not institution and author.get("affiliations"):
                    # Sort affiliations by most recent year and prioritize Swedish institutions
                    affiliations = author["affiliations"]
                    swedish_affiliations = [aff for aff in affiliations 
                                          if aff.get("institution", {}).get("country_code") == "SE"]
                    
                    if swedish_affiliations:
                        # Get the one with most recent year
                        best_aff = max(swedish_affiliations, 
                                     key=lambda x: max(x.get("years", [0])))
                        institution = best_aff["institution"]["display_name"]
                        country = best_aff["institution"]["country_code"]
                    elif affiliations:
                        # Fallback to any recent affiliation
                        best_aff = max(affiliations, 
                                     key=lambda x: max(x.get("years", [0])))
                        institution = best_aff["institution"]["display_name"]
                        country = best_aff["institution"]["country_code"]
                
                # Try email search
                email = search_researcher_email(name, institution or "Swedish University") if name else None
                
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
                    for abstract in abstracts[:3]:  # Limit to 3 abstracts like KTH scraper
                        if not abstract:
                            continue
                        # Comprehensive HTML entity cleanup
                        clean_abstract = (abstract
                            .replace("&amp;", "&")
                            .replace("&lt;", "<")
                            .replace("&gt;", ">")
                            .replace("&quot;", '"')
                            .replace("&apos;", "'")
                            .replace("&#x0D;", " ")
                            .replace("&acute;", "'")
                            .replace("&nbsp;", " ")
                            .replace("\n", " ")  # Remove all newlines
                            .replace("\r", " ")  # Remove carriage returns
                            .replace("\t", " ")  # Remove tabs
                        )
                        # Normalize all whitespace to single spaces
                        clean_abstract = " ".join(clean_abstract.split())
                        
                        # Truncate if too long
                        if len(clean_abstract) > 800:
                            clean_abstract = clean_abstract[:800] + "..."
                        
                        if clean_abstract:  # Only add non-empty abstracts
                            clean_abstracts.append(clean_abstract)
                    
                    # Format abstracts as JSON list for consistency
                    abstracts_text = json.dumps(clean_abstracts, ensure_ascii=False) if clean_abstracts else "[]"
                    
                    row = {
                        "name": " ".join(name.split()) if name else "",
                        "email": email or "",
                        "title": title or "",
                        "institution": " ".join(institution.split()) if institution else "",
                        "country": country or "",
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


