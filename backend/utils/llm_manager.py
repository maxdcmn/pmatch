"""
LLM manager: minimal, concise interface for HTML-to-abstract extraction.

Environment:
- OPENAI_API_KEY (optional). If missing, functions return empty results.
"""

from __future__ import annotations

import os
import logging
from openai import OpenAI
from typing import List, Dict, Any
import json
from db.pg_client import get_conn
from utils.llm_tools import ResearcherMatchTool

logger = logging.getLogger(__name__)

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
    "You are an expert research collaboration assistant. Your mission is to help researchers find the perfect collaboration partners.\n\n"
    
    "CORE CAPABILITIES:\n"
    "- Find researchers using semantic similarity and uploaded CVs/papers\n"
    "- Analyze research compatibility and suggest collaboration opportunities\n"
    "- Help users discover relevant researchers in their field\n"
    
    "AVAILABLE TOOLS:\n"
    "- find_matches_for_user: Find researchers similar to user's uploaded CV/paper (USE THIS FIRST if user_id available)\n"
    "- get_top_matches: Find researchers by research interests or keywords (USE THIS for general searches)\n"
    "- list_institutions: Show available institutions (ONLY use when user specifically asks for institution list)\n"
    
    "TOOL SELECTION RULES:\n"
    "- If user has uploaded a CV/paper (user_id provided), ALWAYS use find_matches_for_user first\n"
    "- If user asks to 'find researchers', 'search for researchers', 'get matches', use get_top_matches with their query\n"
    "- ONLY use list_institutions if user specifically asks 'what institutions' or 'list institutions'\n"
    "- When users ask for researchers in a field (ML, AI, etc.), use get_top_matches with that field as query\n"
    
    "WORKFLOW:\n"
    "1. For users with uploaded content: Use find_matches_for_user to find personalized matches\n"
    "2. For general searches: Use get_top_matches with specific research keywords\n"
    "3. Present researchers with their expertise and contact information\n"
    "4. Suggest potential collaboration opportunities"
    
    "EMAIL REFINEMENT:"
    "When users ask to refine emails, you MUST:"
    "1. Use the refine_email tool to generate a completely new version"
    "2. Include the new email in this exact format:"
    "---"
    "**Current Contact Proposal:**"
    "- **To:** [email]"
    "- **Subject:** [subject]"
    "- **Message:**"
    "[complete new email body]"
    "*This is the current state of your outreach email. You can ask me to modify it further.*"
    
    "SUCCESS METRICS:"
    "- Find researchers with high research compatibility"
    "- Generate emails that reference specific recent papers"
    "- Suggest concrete collaboration opportunities"
    "- Make scientific niche matching the central focus"
    
    "Always be specific, scientific, and actionable in your recommendations."
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
        logger.info(f"Chat with tools: message='{message}', has_user_context={user_context is not None}")
        
        messages = [
            {
                "role": "system", 
                "content": CHAT_SYSTEM_PROMPT,
            },
            {"role": "user", "content": message}
        ]
        
        if user_context:
            logger.info(f"Adding user context: {user_context.get('detected_kind')} - {user_context.get('title')}")
            messages.insert(-1, {
                "role": "system",
                "content": f"User context: {json.dumps(user_context, indent=2)}"
            })
        
        tool_schemas: List[Dict[str, Any]] = [
            s
            for t in self.tools.values()
            for s in (t.function_schemas() if hasattr(t, "function_schemas") else [])
        ]
        
        logger.info(f"Available tools: {[s['name'] for s in tool_schemas]}")

        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=[{"type": "function", "function": s} for s in tool_schemas],
            tool_choice="auto",
            temperature=0,
        )
        
        logger.info(f"OpenAI response received, has tool_calls: {bool(response.choices[0].message.tool_calls)}")
        
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
