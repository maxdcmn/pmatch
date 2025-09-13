"""
Deep Research helper for KTH ML/AI professors.

Provides a notebook-friendly function that attempts to use ONLY
OpenAI's browsing/Deep Research capability. If browsing isn't available
on your API key/model, it logs a clear warning and returns None.

Usage in a Jupyter notebook:

    %pip install -q openai
    import kth_deep_research as kdr
    kdr.configure_logging()
    out = kdr.deep_research_kth_ml_to_csv(
        output_csv="kth_professors.csv",
        min_results=3,
        model="o3-deep-research"  # browsing-enabled model name (if available on your key)
    )
    out

This module will read your key from environment vars in this order:
  - OPENAI_API_KEY
  - OPEN_AI_KEY (and it will set OPENAI_API_KEY from it)
  - .env file entry: OPEN_AI_KEY=...
"""

from __future__ import annotations

import logging
import os
import re
import textwrap
from typing import Optional
import time

try:
    from openai import OpenAI  # type: ignore
    from openai import APITimeoutError  # type: ignore
except Exception:  # pragma: no cover - import-time environment
    OpenAI = None  # type: ignore
    class APITimeoutError(Exception):  # type: ignore
        pass

try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None  # type: ignore


logger = logging.getLogger("kth.deep_research")


def configure_logging(level: int = logging.INFO) -> None:
    """Basic console logging configuration."""
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


def deep_research_kth_ml_to_csv(
    output_csv: str = "kth_professors.csv",
    min_results: int = 3,
    model: str = "o3-deep-research",
    background_timeout_s: int = 1800,
    background_poll_s: float = 2.0,
    client_timeout_s: int = 120,
    client_max_retries: int = 2,
) -> Optional[str]:
    """
    Use ONLY OpenAI browsing/Deep Research to find KTH professors in ML/AI.
    Writes CSV with header: name,email,profile_url. Returns output path on
    success, or None if browsing is not available on the model/key.

    Logging:
      - WARNING if browsing isn't available (returns None)
      - INFO on successful write
      - ERROR if unexpected response format
    """

    if OpenAI is None:  # pragma: no cover - import-time environment
        raise RuntimeError("openai package not installed. Run: pip install openai")

    _load_openai_key()
    client = OpenAI(timeout=client_timeout_s, max_retries=client_max_retries)

    system = textwrap.dedent(
        """
        You are an advanced research agent with web browsing enabled.
        HARD RULES:
        - Sources: ONLY use kth.se and its subdomains; ignore any other domain.
        - Goal: Find current KTH professors whose research includes machine learning or AI.
        - Deliverable: Output ONLY valid CSV (no code fences), header exactly: name,email,profile_url
        - Profiles: Prefer official KTH profile pages (contain /profile/ or under people.kth.se).
        - Email: Include only if public on the KTH page; otherwise leave empty.
        - Count: Provide at least the requested number of rows.
        - Verification: Use only pages you actually opened on kth.se.
        If browsing tools are NOT available in this environment, reply with NO_BROWSING_AVAILABLE and nothing else.
        """
    ).strip()

    user = f"Find at least {min_results} KTH professors in ML/AI and output CSV as specified."

    def _extract_text_from_response_obj(resp) -> Optional[str]:
        """Best-effort extraction of text from a Responses API response object."""
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

    def _wait_for_background(client: "OpenAI", rid: str, timeout_s: int = 300, poll_s: float = 2.0) -> str:
        """Poll Responses API until a background job completes, then return text."""
        deadline = time.time() + timeout_s
        last_status = None
        last_log = 0.0
        while True:
            try:
                resp = client.responses.retrieve(rid)
            except APITimeoutError:
                logger.warning("Polling timed out for job %s; continuing to retry until overall timeout.", rid)
                if time.time() > deadline:
                    raise
                time.sleep(max(1.0, poll_s))
                continue
            except Exception as e:
                # Handle httpx timeouts explicitly if available
                if httpx is not None and isinstance(e, (httpx.ReadTimeout, httpx.ConnectTimeout)):  # type: ignore[attr-defined]
                    logger.warning("HTTP timeout during polling job %s; will retry.", rid)
                    if time.time() > deadline:
                        raise
                    time.sleep(max(1.0, poll_s))
                    continue
                # Other transient errors: log and retry until deadline
                logger.warning("Transient polling error for job %s: %s", rid, e)
                if time.time() > deadline:
                    raise
                time.sleep(max(1.0, poll_s))
                continue
            status = getattr(resp, "status", None)
            if status != last_status:
                logger.debug("responses.get(%s) -> status=%s", rid, status)
                last_status = status
            # Periodic info log every ~30s
            now = time.time()
            if now - last_log > 30:
                logger.info("Deep research job %s status=%s", rid, status)
                last_log = now
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
        return text

    def _call_model() -> str:
        """Call the appropriate API (chat vs responses) for the given model."""
        # o3-deep-research and other o3* models use the Responses API
        use_responses = any(tok in model for tok in ("o3", "deep-research"))
        try:
            if use_responses:
                # Use instructions for system prompt and input for user request.
                # Deep-research models require a tool such as 'web_search_preview'.
                resp = client.responses.create(
                    model=model,
                    instructions=system,
                    input=user,
                    tools=[{"type": "web_search_preview"}],
                    tool_choice="auto",
                    background=True,
                )
                # Background mode: poll by id until completed
                rid = getattr(resp, "id", None)
                if not rid:
                    raise RuntimeError("Missing response id for background job")
                return _wait_for_background(client, rid, timeout_s=background_timeout_s, poll_s=background_poll_s)
            else:
                resp = client.chat.completions.create(
                    model=model,
                    temperature=0,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                return (resp.choices[0].message.content or "").strip()
        except Exception as e:  # pragma: no cover - network/runtime
            logger.error("OpenAI API error: %s", e)
            raise

    text = _call_model()

    if text == "NO_BROWSING_AVAILABLE":
        logger.warning(
            "Browsing/Deep Research not available on your key or chosen model (%s). Returning None.",
            model,
        )
        return None

    # Strip accidental code fences if the model added them
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n```$", "", text).strip()

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines or not lines[0].lower().startswith("name,email,profile_url"):
        logger.error("Unexpected response format; expected CSV header 'name,email,profile_url'.")
        raise ValueError("Unexpected CSV format from model")
    if len(lines) - 1 < min_results:
        logger.warning("Received fewer rows (%d) than requested (%d).", len(lines) - 1, min_results)

    try:
        with open(output_csv, "w", encoding="utf-8", newline="") as f:
            f.write(text if text.endswith("\n") else text + "\n")
    except Exception as e:  # pragma: no cover - filesystem runtime
        logger.error("Failed writing CSV to %s: %s", output_csv, e)
        raise

    logger.info("Wrote CSV to %s (%d rows)", output_csv, max(0, len(lines) - 1))
    return output_csv


__all__ = ["configure_logging", "deep_research_kth_ml_to_csv"]
