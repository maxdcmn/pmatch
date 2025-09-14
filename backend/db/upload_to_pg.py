from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

from pg_client import upsert_profile, clear_null_profiles


def deterministic_id(url: str) -> str:
    return hashlib.md5((url or "").encode("utf-8")).hexdigest()


def _openai_client():
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        return OpenAI()
    except Exception:
        return None


def _embed_mean(texts: List[str]) -> List[float] | None:
    client = _openai_client()
    if not client or not texts:
        return None
    texts = [t.strip() for t in texts if t and t.strip()][:5]
    if not texts:
        return None
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    vecs = [d.embedding for d in resp.data]
    dim = len(vecs[0])
    sums = [0.0] * dim
    for v in vecs:
        for i, val in enumerate(v):
            sums[i] += float(val)
    n = float(len(vecs))
    return [s / n for s in sums]


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Upload CSV to Postgres (pgvector)")
    parser.add_argument("--csv", default=str(Path(__file__).parents[1] / "scraper" / "eu_researchers.csv"))
    args = parser.parse_args()

    rows = []
    with open(args.csv, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for row in rows:
        abstracts_json = row.get("top_abstract") or row.get("abstracts") or ""
        try:
            abstracts = json.loads(abstracts_json) if abstracts_json.strip().startswith("[") else []
        except Exception:
            abstracts = []
        emb = _embed_mean([str(a) for a in abstracts if isinstance(a, str)])

        upsert_profile(
            id=deterministic_id(row.get("profile_url") or row.get("email") or row.get("name") or ""),
            name=row.get("name") or "",
            email=row.get("email") or "",
            title=row.get("title") or "",
            research_area=row.get("research_area") or "",
            profile_url=row.get("profile_url") or "",
            abstracts=abstracts,  # stored as text[]
            embedding=emb,
        )

    print(f"Uploaded {len(rows)} rows to Postgres")
    
    # Clean up profiles with null or empty abstracts
    clear_null_profiles()
    print("Cleared profiles with null or empty abstracts")


if __name__ == "__main__":
    main()


