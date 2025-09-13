"""
Publications utilities — simple, no-LLM version.

Flow:
1) Find a "Publications list" link on the KTH profile page.
2) Open that list page; collect inline abstracts if present.
3) Otherwise, follow a few candidate publication links on known domains and
   extract abstracts via domain-specific selectors and generic fallbacks.

Returns up to `max_items` abstracts; if nothing is found, returns an empty list.
"""

from typing import List, Optional
from urllib.parse import urljoin
import re
import logging

from bs4 import BeautifulSoup


def _t(s) -> str:
    return " ".join((s or "").split())


def _find_publications_link(profile_html: str, profile_url: str) -> Optional[str]:
    """Find a publications list link on the profile page (no LLM)."""
    soup = BeautifulSoup(profile_html, "html.parser")
    keywords = (
        "publikationslista",
        "publikationer",
        "publication list",
        "publications list",
        "publication",
        "publications",
        "/publications",
    )
    for a in soup.find_all("a"):
        text = _t(a.get_text(" ", strip=True)).lower()
        if any(k in text for k in keywords):
            href = a.get("href")
            if href:
                # KTH sometimes uses /profile/{slug}/publications paths
                if href.startswith("/profile/") and "/publications" in href:
                    return urljoin("https://www.kth.se", href)
                return urljoin(profile_url, href)
    return None


async def get_publication_abstracts(page, profile_url: str, profile_html: str, max_items: int = 3) -> List[str]:
    """Return up to `max_items` abstracts collected from publications pages.

    No LLM usage; purely HTML parsing with domain-specific selectors.
    """
    link = _find_publications_link(profile_html, profile_url)
    if not link:
        logging.info("No publications link found for profile: %s", profile_url)
        return []

    resp = await page.goto(link, wait_until="domcontentloaded", timeout=45000)
    if not resp or not (200 <= resp.status < 400):
        logging.warning("Failed to open publications list: %s", link)
        return []
    await page.wait_for_timeout(300)
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    # Inline abstracts on the publications list page
    inline: List[str] = []
    for el in soup.select('details, [class*="abstract"], [id*="abstract"], [class*="sammanfatt"], [id*="sammanfatt"]'):
        text = _t(el.get_text(" ", strip=True))
        if len(text) > 30 and ("abstract" in text.lower() or "sammanfatt" in text.lower()):
            inline.append(text)
            if len(inline) >= max_items:
                break
    if inline:
        logging.info("Found %d inline abstracts on list page: %s", len(inline), link)
        return inline[:max_items]

    # Collect candidate links to individual publications
    anchors = [
        *soup.select("ul li a[href]"),
        *soup.select("ol li a[href]"),
        *soup.select("article a[href]"),
        *soup.select("table a[href]"),
    ]
    seen = set()
    pub_links: List[str] = []
    allow = re.compile(
        r"(doi\.org/|arxiv\.org/abs/|ieeexplore\.ieee\.org/document/|dl\.acm\.org/doi/|"
        r"link\.springer\.com/|springer\.com/|sciencedirect\.com/science/article/|"
        r"onlinelibrary\.wiley\.com/doi/|tandfonline\.com/doi/|nature\.com/|"
        r"scholar\.google\.com/|diva-portal\.org/)"
    )
    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        url = urljoin(link, href)
        # Skip obvious non-publication links (mailto, anchors)
        if url.startswith("mailto:") or "#" in href:
            continue
        if url in seen:
            continue
        seen.add(url)
        if allow.search(url):
            pub_links.append(url)
        if len(pub_links) >= max_items:
            break
    logging.info("Candidate publication links: %d", len(pub_links))

    abstracts: List[str] = []
    for url in pub_links:
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            if not resp or not (200 <= resp.status < 400):
                continue
            await page.wait_for_timeout(200)
            phtml = await page.content()
            psoup = BeautifulSoup(phtml, "html.parser")

            # Domain-specific selectors
            u = url.lower()
            abstract_text = None
            if "arxiv.org/abs/" in u:
                el = psoup.select_one('blockquote.abstract, meta[name="citation_abstract"]')
                abstract_text = _t(el.get("content") if el and el.name == 'meta' else (el.get_text(" ", strip=True) if el else ""))
            elif "ieeexplore.ieee.org/document/" in u:
                el = psoup.select_one('.abstract-text, meta[name="citation_abstract"]')
                abstract_text = _t(el.get("content") if el and el.name == 'meta' else (el.get_text(" ", strip=True) if el else ""))
            elif "dl.acm.org/doi/" in u:
                el = psoup.select_one('section.abstract, .abstractInFull')
                abstract_text = _t(el.get_text(" ", strip=True)) if el else None
            elif "springer" in u or "link.springer.com" in u:
                el = psoup.select_one('section#Abs1, section.Abstract')
                abstract_text = _t(el.get_text(" ", strip=True)) if el else None
            elif "sciencedirect.com" in u:
                el = psoup.select_one('div.Abstracts, div.Abstracts p')
                abstract_text = _t(el.get_text(" ", strip=True)) if el else None
            elif "wiley.com/doi/" in u:
                el = psoup.select_one('section.article-section__abstract, div.article-section__content')
                abstract_text = _t(el.get_text(" ", strip=True)) if el else None
            elif "tandfonline.com/doi/" in u:
                el = psoup.select_one('div.abstractSection, section.abstract')
                abstract_text = _t(el.get_text(" ", strip=True)) if el else None
            elif "nature.com" in u:
                el = psoup.select_one('div#Abs1-content, section#abstract')
                abstract_text = _t(el.get_text(" ", strip=True)) if el else None
            elif "doi.org/" in u:
                # some DOIs redirect client-side; try meta
                meta = psoup.find("meta", attrs={"name": "dc.Description"}) or psoup.find("meta", attrs={"name": "description"})
                abstract_text = _t(meta.get("content")) if meta and meta.get("content") else None

            # Generic fallbacks
            if not abstract_text:
                for h in psoup.find_all(["h1", "h2", "h3", "h4"]):
                    t = _t(h.get_text(" ", strip=True)).lower()
                    if "abstract" in t or "sammanfattning" in t:
                        sib = h.find_next(["p", "div"]) or h.parent
                        if sib:
                            abstract_text = _t(sib.get_text(" ", strip=True))
                            break
            if not abstract_text:
                el = psoup.select_one('[class*="abstract"], [id*="abstract"], [class*="sammanfatt"], [id*="sammanfatt"]')
                if el:
                    abstract_text = _t(el.get_text(" ", strip=True))
            if not abstract_text:
                meta = psoup.find("meta", attrs={"name": "description"})
                if meta and meta.get("content"):
                    abstract_text = _t(meta["content"])

            if abstract_text and len(abstract_text) > 30:
                abstracts.append(abstract_text)
            if len(abstracts) >= max_items:
                break
        except Exception as e:
            logging.exception("Error parsing publication %s: %s", url, e)
            continue

    return abstracts[:max_items]

