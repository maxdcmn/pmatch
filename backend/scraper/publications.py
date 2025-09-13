"""
Publications utilities.

Select a publications source for a KTH profile using an LLM + heuristics in the
following priority:
1) A publications link on the profile page
2) Google Scholar profile link
3) ORCID profile link

If none exist, return None (caller should skip this profile). Otherwise, visit
the selected source page and gather up to three recent abstracts.
"""

from typing import List, Optional, Tuple
from urllib.parse import urljoin
import re
import logging

from bs4 import BeautifulSoup
try:
    from ..utils.llm_manager import extract_abstracts_with_llm, choose_publication_links  # type: ignore
except Exception:
    try:
        from utils.llm_manager import extract_abstracts_with_llm, choose_publication_links  # type: ignore
    except Exception:  # last-resort no-op fallback
        def extract_abstracts_with_llm(_: str, model: str = "gpt-4o-mini"):
            return []
        def choose_publication_links(_: list, __: str, model: str = "gpt-4o-mini"):
            return []


def _t(s) -> str:
    return " ".join((s or "").split())


def _find_anchors(profile_html: str, base_url: str) -> List[Tuple[str, str]]:
    """Return list of (text, absolute_url) anchors from the profile page."""
    soup = BeautifulSoup(profile_html, "html.parser")
    out: List[Tuple[str, str]] = []
    for a in soup.find_all("a"):
        text = _t(a.get_text(" ", strip=True))
        href = a.get("href")
        if not href:
            continue
        out.append((text, urljoin(base_url, href)))
    return out


def _choose_source_with_llm(anchors: List[Tuple[str, str]], page_text: str) -> List[str]:
    """Use LLM to select likely publications-related links from anchors.

    Returns list of URLs (may be empty if no LLM or nothing selected).
    """
    if not anchors:
        return []
    candidates = [f"{t} | {u}" for t, u in anchors]
    return choose_publication_links(candidates, page_text)


def _pick_best_source(anchors: List[Tuple[str, str]], llm_urls: List[str]) -> Optional[str]:
    """Pick best source URL in required priority order."""
    # Heuristic pass over anchors first
    pubs_keywords = (
        "publikationslista",
        "publikationer",
        "publication list",
        "publications list",
        "publication",
        "publications",
        "research outputs",
        "/publications",
    )
    scholar_kw = ("scholar.google.com", "google scholar")
    orcid_kw = ("orcid.org/",)

    def find_in(listing: List[Tuple[str, str]], kws) -> Optional[str]:
        for text, url in listing:
            low = (text or "").lower() + " " + (url or "").lower()
            if any(k in low for k in kws):
                return url
        return None

    # 1) Publications link on profile
    url = find_in(anchors, pubs_keywords)
    if url:
        return url
    # 2) Google Scholar
    url = find_in(anchors, scholar_kw)
    if url:
        return url
    # 3) ORCID
    url = find_in(anchors, orcid_kw)
    if url:
        return url

    # Fall back to LLM-selected URLs in the same priority order
    def find_in_llm(urls: List[str], kws) -> Optional[str]:
        for url in urls:
            low = url.lower()
            if any(k in low for k in kws):
                return url
        return None

    url = find_in_llm(llm_urls, pubs_keywords)
    if url:
        return url
    url = find_in_llm(llm_urls, scholar_kw)
    if url:
        return url
    url = find_in_llm(llm_urls, orcid_kw)
    if url:
        return url
    return None


async def get_publication_abstracts(page, profile_url: str, profile_html: str, max_items: int = 3) -> Optional[List[str]]:
    """Return up to `max_items` abstracts or None if no publications source found."""
    soup_profile = BeautifulSoup(profile_html, "html.parser")
    anchors = _find_anchors(profile_html, profile_url)
    llm_urls = _choose_source_with_llm(anchors, soup_profile.get_text(" ", strip=True))
    link = _pick_best_source(anchors, llm_urls)
    if not link:
        preview = "; ".join([f"{t[:40]} -> {u[:60]}" for t, u in anchors[:6]])
        logging.info(
            "No publications/Scholar/ORCID link found for profile: %s (anchors=%d) Preview: %s",
            profile_url,
            len(anchors),
            preview,
        )
        return None

    logging.info("Visiting publications source: %s", link)
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
        return inline[:max_items] or extract_abstracts_with_llm(soup.get_text(" ", strip=True))[:max_items]

    # Collect candidate links to individual publications or lists. Build LLM-assisted shortlist.
    anchors = [
        *soup.select("ul li a[href]"),
        *soup.select("ol li a[href]"),
        *soup.select("article a[href]"),
        *soup.select("table a[href]"),
    ]
    seen = set()
    pub_links: List[str] = []
    allow = re.compile(r"(doi\.org/|arxiv\.org/abs/|ieeexplore\.ieee\.org/document/|dl\.acm\.org/doi/|link\.springer\.com/|springer\.com/|sciencedirect\.com/science/article/|onlinelibrary\.wiley\.com/doi/|tandfonline\.com/doi/|nature\.com/|scholar\.google\.com/|diva-portal\.org/)")
    candidates_for_llm: List[str] = []
    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        url = urljoin(link, href)
        # Skip obvious non-publication links (filters, mailto, anchors)
        if url.startswith("mailto:") or "#" in href:
            continue
        candidates_for_llm.append(f"{_t(a.get_text(' ', strip=True))} | {url}")
        if not allow.search(url):
            # keep for LLM decision; do not continue
            pass
        if url in seen:
            continue
        seen.add(url)
        if allow.search(url):
            pub_links.append(url)
        if len(pub_links) >= max_items:
            break
    # If none or few allowed links, ask LLM to pick likely links (e.g., Google Scholar or KTH list pages)
    if len(pub_links) < max_items:
        llm_urls = choose_publication_links(candidates_for_llm, soup.get_text(" ", strip=True))
        for u in llm_urls:
            if u not in seen:
                pub_links.append(u)
                seen.add(u)
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
            else:
                # LLM fallback
                llm_abs = extract_abstracts_with_llm(psoup.get_text(" ", strip=True))
                abstracts.extend(llm_abs[:1])
            if len(abstracts) >= max_items:
                break
        except Exception as e:
            logging.exception("Error parsing publication %s: %s", url, e)
            continue

    return abstracts[:max_items]
