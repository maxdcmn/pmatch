from __future__ import annotations

from typing import Any, Dict, List, Optional, Callable
from db.pg_client import search_profiles, get_distinct_institutions, get_user_by_id, find_matching_researchers
from openai import OpenAI
import os


class ResearcherMatchTool:

    def __init__(self, db_client):
        self.db_client = db_client

    def get_top_matches(
        self,
        query: str,
        top_k: int = 5,
        institution: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            inst_norm = institution.strip() if isinstance(institution, str) else None
            if inst_norm:
                available = get_distinct_institutions()
                lower_map = {x.lower(): x for x in available}
                if inst_norm.lower() not in lower_map:
                    return {"error": "invalid_institution", "message": f"Institution not found: {institution}", "available_institutions": available}
                inst_norm = lower_map[inst_norm.lower()]

            # Embed the query
            embedding = self._embed_query(query)
            if not embedding:
                return {"error": "embedding_failed", "message": "Failed to generate embedding for query"}

            rows = search_profiles(embedding, top_k=top_k)
            results: List[Dict[str, Any]] = []
            for r in rows:
                if inst_norm and (r.get("institution") or "") != inst_norm:
                    continue
                results.append({
                    "id": str(r.get("id")),
                    "name": r.get("name"),
                    "email": r.get("email"),
                    "title": r.get("title"),
                    "research_area": r.get("research_area"),
                    "institution": r.get("institution"),
                    "country": r.get("country"),
                    "profile_url": r.get("profile_url"),
                    "abstracts": r.get("abstracts"),
                    "score": float(r.get("score", 0.0)),
                })
            return {"query": query, "top_k": top_k, "institution": inst_norm, "results": results}
        except Exception as e:
            return {"error": f"get_top_matches failed: {e}", "query": query, "top_k": top_k}

    def list_institutions(self) -> Dict[str, Any]:
        try:
            institutions = get_distinct_institutions()
            return {"institutions": institutions, "count": len(institutions)}
        except Exception as e:
            return {"error": f"list_institutions failed: {e}"}

    def find_matches_for_user(
        self,
        user_id: str,
        top_k: int = 10,
        institution: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Find researchers that match a user's uploaded CV/paper."""
        try:
            # Get user data
            user_data = get_user_by_id(user_id)
            if not user_data:
                return {"error": "user_not_found", "message": f"User {user_id} not found"}

            if not user_data.get("embedding"):
                return {"error": "no_embedding", "message": "User has no embedding - upload a CV or paper first"}

            # Debug embedding data
            embedding_data = user_data["embedding"]
            logger.info(f"User embedding type: {type(embedding_data)}")
            logger.info(f"User embedding sample: {str(embedding_data)[:100]}...")
            
            # Convert embedding if it's stored as string
            if isinstance(embedding_data, str):
                import json
                try:
                    embedding_data = json.loads(embedding_data)
                    logger.info(f"Converted embedding from string, new type: {type(embedding_data)}")
                except Exception as e:
                    logger.error(f"Failed to parse embedding string: {e}")
                    return {"error": "embedding_parse_failed", "message": f"Failed to parse user embedding: {e}"}

            # Filter by institution if specified
            inst_norm = institution.strip() if isinstance(institution, str) else None
            if inst_norm:
                available = get_distinct_institutions()
                lower_map = {x.lower(): x for x in available}
                if inst_norm.lower() not in lower_map:
                    return {"error": "invalid_institution", "message": f"Institution not found: {institution}", "available_institutions": available}
                inst_norm = lower_map[inst_norm.lower()]

            # Find matching researchers
            rows = find_matching_researchers(embedding_data, top_k=top_k)
            results: List[Dict[str, Any]] = []
            for r in rows:
                if inst_norm and (r.get("institution") or "") != inst_norm:
                    continue
                results.append({
                    "id": str(r.get("id")),
                    "name": r.get("name"),
                    "email": r.get("email"),
                    "title": r.get("title"),
                    "research_area": r.get("research_area"),
                    "institution": r.get("institution"),
                    "country": r.get("country"),
                    "profile_url": r.get("profile_url"),
                    "abstracts": r.get("abstracts"),
                    "similarity_score": float(r.get("similarity_score", 0.0)),
                })

            return {
                "user_id": user_id,
                "user_title": user_data.get("title"),
                "user_kind": user_data.get("detected_kind"),
                "top_k": top_k,
                "institution": inst_norm,
                "results": results,
                "match_count": len(results)
            }
        except Exception as e:
            return {"error": f"find_matches_for_user failed: {e}", "user_id": user_id}

    def _embed_query(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a text query."""
        try:
            if not os.getenv("OPENAI_API_KEY"):
                return None
            client = OpenAI()
            resp = client.embeddings.create(model="text-embedding-3-small", input=[text])
            return resp.data[0].embedding
        except Exception:
            return None

    def function_schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "get_top_matches",
                "description": "Get top researcher matches for a natural language query. Optionally filter by institution.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language query describing research interests"},
                        "top_k": {"type": "integer", "description": "Number of results to return", "default": 5},
                        "institution": {"type": "string", "description": "Optional institution filter; must be one of the available institutions"}
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "find_matches_for_user",
                "description": "Find researchers that match a specific user's uploaded CV or paper based on semantic similarity. This is the primary tool for personalized matching.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "The user ID from the upload response"},
                        "top_k": {"type": "integer", "description": "Number of results to return", "default": 10},
                        "institution": {"type": "string", "description": "Optional institution filter; must be one of the available institutions"}
                    },
                    "required": ["user_id"],
                },
            },
            {
                "name": "list_institutions",
                "description": "List all available research institutions in the database",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        ]

    def get_functions(self) -> Dict[str, Callable]:
        return {
            "get_top_matches": self.get_top_matches,
            "find_matches_for_user": self.find_matches_for_user,
            "list_institutions": self.list_institutions,
        }
