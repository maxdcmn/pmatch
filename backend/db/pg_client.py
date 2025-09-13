from __future__ import annotations

import os
from typing import List, Dict, Optional

import psycopg
from psycopg.rows import dict_row


def get_conn() -> psycopg.Connection:
    dsn = os.getenv(
        "DATABASE_URL",
        "postgresql://pmatch:pmatch@localhost:5432/pmatch",
    )
    return psycopg.connect(dsn, row_factory=dict_row)


def upsert_profile(
    *,
    id: str,
    name: str,
    email: str,
    title: str,
    research_area: str,
    profile_url: str,
    abstracts: List[str],
    embedding: Optional[List[float]],
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO profiles (id, name, email, title, research_area, profile_url, abstracts, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                  name = EXCLUDED.name,
                  email = EXCLUDED.email,
                  title = EXCLUDED.title,
                  research_area = EXCLUDED.research_area,
                  profile_url = EXCLUDED.profile_url,
                  abstracts = EXCLUDED.abstracts,
                  embedding = EXCLUDED.embedding
                """,
                (
                    id,
                    name,
                    email,
                    title,
                    research_area,
                    profile_url,
                    abstracts,
                    embedding,
                ),
            )


def _vector_literal(vec: List[float]) -> str:
    # pgvector accepts "[v1, v2, ...]" text literal
    return "[" + ", ".join(str(float(x)) for x in vec) + "]"


def search_profiles(query_embedding: List[float], top_k: int = 5) -> List[Dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            vec_text = _vector_literal(query_embedding)
            cur.execute(
                """
                SELECT *, 1 - (embedding <=> %s::vector) AS score
                FROM profiles
                WHERE embedding IS NOT NULL
                ORDER BY embedding <-> %s::vector
                LIMIT %s
                """,
                (vec_text, vec_text, top_k),
            )
            return cur.fetchall()


