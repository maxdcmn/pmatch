"""
LLM manager: minimal, concise interface for HTML-to-abstract extraction.

Environment:
- OPENAI_API_KEY (optional). If missing, functions return empty results.
"""

from __future__ import annotations

import os
from openai import OpenAI
from typing import List, Dict, Any
import json
from db.pg_client import get_conn
from utils.llm_tools import ResearcherMatchTool

EXTRACTION_SYSTEM_PROMPT = (
    "You are an information extraction agent. Given raw HTML or visible text of a "
    "publication page or publications list, extract concise English abstracts. "
    "Return a JSON array of strings (each string is one abstract). If no abstracts "
    "exist, return an empty JSON array. Keep each abstract under 1200 characters."
)

LINK_SELECTION_SYSTEM_PROMPT = (
    "You are a link selector. You will receive a list of candidate links from a "
    "researcher profile page as 'TEXT | URL' lines plus some page text. "
    "Return a JSON array of URLs that are most likely to lead to a publications "
    "list or publication entries. Prefer links containing words like "
    "'Publikationslista', 'Publications', 'Google Scholar', 'Research outputs'."
)

CHAT_SYSTEM_PROMPT = (
    "You are an expert research matching assistant. You have access to a database of researchers and can:"
    "- Search for researchers using semantic similarity"
    "- Find best matches for users based on their profiles"
    "- Analyze compatibility between users and researchers"
    "- Generate personalized outreach messages"
    "- Test different matching scenarios"
    "Your goal is to find a specific researcher for the user to reach out to."
    "Use the available tools to help users find the best research collaborations."
    "Available tool functions: get_top_matches, list_institutions."
)

def _has_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def extract_abstracts_with_llm(html_or_text: str, model: str = "gpt-4o-mini") -> List[str]:
    if not _has_key() or not html_or_text or len(html_or_text) < 40:
        return []
    try:
        client = OpenAI()
        content = html_or_text[:100_000]
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            temperature=0,
        )
        text = resp.choices[0].message.content or "[]"
        arr = json.loads(text) if text.strip().startswith("[") else []
        return [str(x)[:1200] for x in arr if isinstance(x, str)]
    except Exception:
        return []


def choose_publication_links(candidate_lines: List[str], page_text: str, model: str = "gpt-4o-mini") -> List[str]:
    if not _has_key() or not candidate_lines:
        return []
    try:
        client = OpenAI()
        lines = "\n".join(candidate_lines)
        content = f"Candidates:\n{lines}\n\nPage Text (truncated):\n{page_text[:4000]}\n\nReturn JSON array of URLs only."
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": LINK_SELECTION_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            temperature=0,
        )
        text = resp.choices[0].message.content or "[]"
        urls = json.loads(text) if text.strip().startswith("[") else []
        return [u for u in urls if isinstance(u, str) and u.startswith("http")]
    except Exception:
        return []


class LLMManager:
    def __init__(self):
        self.client = OpenAI()
        self.db_client = get_conn()
        self.tools = {
            "match_tool": ResearcherMatchTool(self.db_client)
        }
    
    async def chat_with_tools(self, message: str, user_context: Dict = None) -> Dict:    
        messages = [
            {
                "role": "system", 
                "content": CHAT_SYSTEM_PROMPT,
            },
            {"role": "user", "content": message}
        ]
        
        if user_context:
            messages.insert(-1, {
                "role": "system",
                "content": f"User context: {json.dumps(user_context, indent=2)}"
            })
        
        tool_schemas: List[Dict[str, Any]] = [
            s
            for t in self.tools.values()
            for s in (t.function_schemas() if hasattr(t, "function_schemas") else [])
        ]

        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=[{"type": "function", "function": s} for s in tool_schemas],
            tool_choice="auto",
            temperature=0,
        )
        
        if response.choices[0].message.tool_calls:
            return await self._handle_tool_calls(response, messages)
        else:
            return {
                "response": response.choices[0].message.content,
                "tools_used": []
            }
    
    async def _handle_tool_calls(self, response, messages):
        tool_calls = response.choices[0].message.tool_calls
        messages.append(response.choices[0].message)
        results_list = []
        
        dispatch: Dict[str, Any] = {
            name: fn
            for t in getattr(self, "tools", {}).values()
            for name, fn in (getattr(t, "get_functions")() if hasattr(t, "get_functions") else {}).items()
        }

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            try:
                function_args = json.loads(tool_call.function.arguments or "{}")
                if not isinstance(function_args, dict):
                    function_args = {}
            except Exception:
                function_args = {}
            fn = dispatch.get(function_name)
            if callable(fn):
                try:
                    result = fn(**function_args)
                except Exception as e:
                    result = {"error": f"{function_name} failed: {e}"}
            else:
                result = {"error": f"Unknown function: {function_name}"}

            try:
                results_list.append(result)
            except Exception:
                results_list.append({"error": "failed to capture result"})

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, indent=2)
            })
        
        final_response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        
        return {
            "response": final_response.choices[0].message.content,
            "tools_used": [tc.function.name for tc in tool_calls],
            "tool_results": results_list
        }
