"""
KTH directory scraper (compact).

Fetch ~20 profiles (professors, postdocs, researchers) from the directory page,
visit each profile, and write CSV with:
name, email, title, research_area, profile_url, top_publication, top_abstract.
"""

import asyncio
import csv
from pathlib import Path
import hashlib
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from tenacity import retry, stop_after_attempt, wait_exponential


DIRECTORY_URL = "https://www.kth.se/directory/j/jh"
OUTPUT_CSV = str(Path(__file__).with_name("kth_researchers.csv"))
MAX_PROFILES = 100
TITLES_INCLUDE = (
    "professor",
    "universitetslektor",
    "doktorand",
    "postdoktor",
    "research",
    "forskare",
)


def _text(el) -> str:
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def shortlist_row(row: Dict[str, str]) -> bool:
    title = (row.get("title") or "").lower()
    return any(key in title for key in TITLES_INCLUDE)


def hash_id(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


@retry(wait=wait_exponential(multiplier=0.5, max=8), stop=stop_after_attempt(3))
async def fetch_html(page, url: str) -> str:
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    if not resp or not (200 <= resp.status < 400):
        raise RuntimeError(f"Bad status {resp.status if resp else 'N/A'} for {url}")
    await page.wait_for_timeout(300)
    return await page.content()


def parse_directory(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="staff-table") or soup.find("table")
    results: List[Dict[str, str]] = []
    if not table:
        return results
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        avatar_td, last_td, first_td, title_td, email_td = tds[0], tds[1], tds[2], tds[3], tds[4]
        profile_a = first_td.find("a") or last_td.find("a") or avatar_td.find("a")
        profile_url = profile_a.get("href", "") if profile_a else ""
        if profile_url.startswith("/"):
            profile_url = f"https://www.kth.se{profile_url}"
        row = {
            "name": f"{_text(first_td)} {_text(last_td)}".strip(),
            "title": _text(title_td),
            "email": _text(email_td),
            "profile_url": profile_url,
        }
        if shortlist_row(row):
            results.append(row)
    return results


def parse_profile(html: str) -> Dict[str, Optional[str]]:
    soup = BeautifulSoup(html, "html.parser")
    research_area = None
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        research_area = meta_desc["content"].strip()
    if not research_area:
        for sel in [".article__ingress", ".lead", ".ingress", "p"]:
            node = soup.select_one(sel)
            if node and len(_text(node)) > 40:
                research_area = _text(node)
                break

    top_publication = None
    top_abstract = None
    pubs_section = None
    for h in soup.find_all(["h2", "h3"]):
        txt = _text(h).lower()
        if "publication" in txt or "publikation" in txt:
            pubs_section = h.find_next()
            break
    if pubs_section:
        first_item = pubs_section.find(["li", "p", "article"]) or pubs_section
        if first_item:
            top_publication = _text(first_item)
            details = first_item.find("details") or first_item.find_next("details")
            if details:
                top_abstract = _text(details)

    return {
        "research_area": research_area,
        "top_publication": top_publication,
        "top_abstract": top_abstract,
    }


async def scrape() -> List[Dict[str, Any]]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        dir_html = await fetch_html(page, DIRECTORY_URL)
        people = parse_directory(dir_html)
        seen: set[str] = set()
        results: List[Dict[str, Any]] = []
        for person in people:
            if len(results) >= MAX_PROFILES:
                break
            url = person.get("profile_url")
            if not url:
                continue
            pid = hash_id(url)
            if pid in seen:
                continue
            try:
                html = await fetch_html(page, url)
                extra = parse_profile(html)
            except Exception:
                extra = {"research_area": None, "top_publication": None, "top_abstract": None}
            row = {**person, **extra}
            results.append(row)
            seen.add(pid)
        await context.close()
        await browser.close()
        return results


def write_csv(rows: List[Dict[str, Any]], path: str) -> None:
    if not rows:
        return
    fields = [
        "name",
        "email",
        "title",
        "research_area",
        "profile_url",
        "top_publication",
        "top_abstract",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for r in rows:
            clean = {k: " ".join(str(r.get(k) or "").split()) for k in fields}
            writer.writerow(clean)


async def main() -> None:
    rows = await scrape()
    write_csv(rows, OUTPUT_CSV)


if __name__ == "__main__":
    asyncio.run(main())