from __future__ import annotations

from typing import Any, Dict, List, Optional, Callable
from db.pg_client import search_profiles, get_distinct_institutions


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

            # TODO: Add profile embedding and search
            # rows = search_profiles(emb, top_k=top_k)
            # results: List[Dict[str, Any]] = []
            # for r in rows:
            #     if inst_norm and (r.get("institution") or "") != inst_norm:
            #         continue
            #     results.append({
            #         "id": str(r.get("id")),
            #         "name": r.get("name"),
            #         "email": r.get("email"),
            #         "title": r.get("title"),
            #         "research_area": r.get("research_area"),
            #         "institution": r.get("institution"),
            #         "country": r.get("country"),
            #         "profile_url": r.get("profile_url"),
            #         "abstracts": r.get("abstracts"),
            #         "score": float(r.get("score", 0.0)),
            #     })
            # return {"query": query, "top_k": top_k, "institution": inst_norm, "results": results}
            return {"error": "not implemented", "query": query, "top_k": top_k}
        except Exception as e:
            return {"error": f"get_top_matches failed: {e}", "query": query, "top_k": top_k}

    def list_institutions(self) -> Dict[str, Any]:
        try:
            institutions = get_distinct_institutions()
            return {"institutions": institutions, "count": len(institutions)}
        except Exception as e:
            return {"error": f"list_institutions failed: {e}"}

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
                "name": "list_institutions",
                "description": "List all available research institutions in the database",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        ]

    def get_functions(self) -> Dict[str, Callable]:
        return {
            "get_top_matches": self.get_top_matches,
            "list_institutions": self.list_institutions,
        }
