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
    institution: str,
    country: str,
    profile_url: str,
    abstracts: List[str],
    embedding: Optional[List[float]],
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Insert into profiles table with abstracts
            cur.execute(
                """
                INSERT INTO profiles (id, name, email, title, research_area, institution, country, profile_url, abstracts, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (profile_url) DO NOTHING
                """,
                (
                    id,
                    name,
                    email,
                    title,
                    research_area,
                    institution,
                    country,
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

def clear_null_profiles() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Clear profiles with null or empty abstracts
            cur.execute(
                "DELETE FROM profiles WHERE abstracts IS NULL OR abstracts = '{}'::text[]",
            )
            conn.commit()


def upsert_user(
    *,
    id: str,
    filename: str,
    content_type: str,
    detected_kind: str,
    title: str,
    content: str,
    embedding: Optional[List[float]],
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (id, filename, content_type, detected_kind, title, content, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                  filename = EXCLUDED.filename,
                  content_type = EXCLUDED.content_type,
                  detected_kind = EXCLUDED.detected_kind,
                  title = EXCLUDED.title,
                  content = EXCLUDED.content,
                  embedding = EXCLUDED.embedding,
                  updated_at = NOW()
                """,
                (id, filename, content_type, detected_kind, title, content, embedding),
            )


def get_user_by_id(user_id: str) -> Optional[Dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return cur.fetchone()


def find_matching_researchers(user_embedding: List[float], top_k: int = 10) -> List[Dict]:
    """Find researchers similar to user's CV/paper."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            vec_text = _vector_literal(user_embedding)
            cur.execute(
                """
                SELECT *, 1 - (embedding <=> %s::vector) AS similarity_score
                FROM profiles
                WHERE embedding IS NOT NULL
                ORDER BY embedding <-> %s::vector
                LIMIT %s
                """,
                (vec_text, vec_text, top_k),
            )
            return cur.fetchall()


def get_distinct_institutions() -> List[str]:
    """Return distinct non-empty institution names from profiles."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT institution
                FROM profiles
                WHERE institution IS NOT NULL AND institution <> ''
                ORDER BY institution
                """
            )
            rows = cur.fetchall()
            # rows are dict_row objects like {'institution': 'KTH'}
            return [str(r["institution"]) for r in rows if r.get("institution")]
