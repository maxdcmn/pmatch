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
from urllib.parse import urljoin, urlparse, urlunparse
import re
import logging

from bs4 import BeautifulSoup


def _t(s) -> str:
    return " ".join((s or "").split())


def _block_text(el) -> str:
    """Return full text of an element, preserving line breaks.

    Uses "\n" as separator to keep the whole abstract intact.
    """
    if not el:
        return ""
    return el.get_text("\n", strip=True)


def _heading_next_paragraph(soup: BeautifulSoup) -> Optional[str]:
    """Find a heading containing 'Abstract'/'Sammanfattning' and return next <p> text."""
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        t = _t(h.get_text(" ", strip=True)).lower()
        if "abstract" in t or "sammanfattning" in t or "sammanfatt" in t or "summary" in t:
            p = h.find_next("p")
            if p:
                return _block_text(p)
    return None


def _is_plausible_abstract(text: str) -> bool:
    """Heuristically decide if text looks like a real abstract, not a category label."""
    if not text:
        return False
    t = " ".join(text.split())
    # Filter out common Swedish category headings from KTH lists
    bad_prefix = (
        "refereegranskade",
        "icke refereegranskade",
        "artiklar",
        "konferensbidrag",
        "kapitel",
        "avhandlingar",
        "rapporter",
        "övriga",
        "böcker",
        "patent",
        "godkända patent",
        "publikationslista",
    )
    low = t.lower()
    if any(low.startswith(bp) for bp in bad_prefix):
        return False
    if low.startswith("abstract page"):
        return False
    # Basic shape: length and sentence punctuation
    if len(t) < 120:
        return False
    if sum(1 for c in t if c in ".!?;:") < 2:
        return False
    # Avoid shouting blocks
    letters = [c for c in t if c.isalpha()]
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / max(1, len(letters))
        if upper_ratio > 0.6:
            return False
    return True


async def _try_expand_abstract(page) -> None:
    """Best-effort clicks to reveal hidden abstract sections on dynamic pages."""
    try:
        # Click common toggles
        selectors = [
            "summary:has-text('Abstract')",
            "summary:has-text('Sammanfatt')",
            "button:has-text('Abstract')",
            "button:has-text('Sammanfatt')",
            "a:has-text('Abstract')",
            "a:has-text('Sammanfatt')",
            "[aria-controls*=""abstract""]",
            "[data-abstract-toggle]",
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    await loc.click(timeout=500)
                    await page.wait_for_timeout(200)
            except Exception:
                pass
        # Expand first few collapsed <details>
        try:
            count = await page.locator("details:not([open]) > summary").count()
            for i in range(min(count, 3)):
                await page.locator("details:not([open]) > summary").nth(i).click()
                await page.wait_for_timeout(150)
        except Exception:
            pass
    except Exception:
        pass


def _heading_next_paragraph(soup: BeautifulSoup) -> Optional[str]:
    """Find a heading containing 'Abstract'/'Sammanfattning' and return next <p> text."""
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        t = _t(h.get_text(" ", strip=True)).lower()
        if "abstract" in t or "sammanfattning" in t or "sammanfatt" in t:
            p = h.find_next("p")
            if p:
                return _t(p.get_text(" ", strip=True))
    return None


def _normalize_profile_base(url: str) -> str:
    """Normalize a KTH profile URL to its base, removing language hints.

    Examples:
    - https://www.kth.se/profile/abc?l=en -> https://www.kth.se/profile/abc
    - https://www.kth.se/profile/abc/en -> https://www.kth.se/profile/abc
    - https://www.kth.se/profile/abc/publications -> https://www.kth.se/profile/abc
    """
    p = urlparse(url)
    # strip query (e.g., ?l=en)
    path = p.path.rstrip('/')
    # keep only /profile/<slug>
    m = re.match(r"^(/profile/[^/]+)", path)
    base = m.group(1) if m else path
    # strip trailing language segment if present (e.g., /en or /sv)
    base = re.sub(r"/(en|sv)$", "", base)
    return urlunparse((p.scheme, p.netloc, base, '', '', ''))


def _find_publications_link(profile_html: str, profile_url: str) -> Optional[str]:
    """Find a publications list link on the profile page (no LLM).

    If an anchor looks like a publications link but lacks '/publications' and
    contains a language spec, normalize to base and append '/publications'.
    As final fallback, use <profile>/publications.
    """
    soup = BeautifulSoup(profile_html, "html.parser")
    # First: if there is a direct DiVA record link on the profile, prefer it
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        abs_url = urljoin(profile_url, href)
        low = abs_url.lower()
        if ("diva-portal.org" in low) and ("record.jsf" in low) and ("pid=diva2:" in low):
            logging.info("Profile has direct DiVA record link: %s", abs_url)
            return abs_url
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
        href = a.get("href")
        if not href:
            continue
        abs_url = urljoin(profile_url, href)
        if any(k in text for k in keywords) or "/publications" in abs_url:
            # If the found URL already points to a publications page, use it
            if "/publications" in abs_url:
                logging.info("Found publications link on profile: %s", abs_url)
                return abs_url
            # Otherwise normalize base and construct /publications
            base = _normalize_profile_base(abs_url)
            constructed = f"{base}/publications"
            logging.info("Constructed publications link from anchor: %s", constructed)
            return constructed
    # Fallback: try appending "/publications" to the current profile URL
    try:
        base = _normalize_profile_base(profile_url)
        fallback = f"{base}/publications"
        logging.info("Using fallback publications URL: %s", fallback)
        return fallback
    except Exception:
        return None


async def get_publication_abstracts(page, profile_url: str, profile_html: str, max_items: int = 3) -> List[str]:
    """Return up to `max_items` abstracts collected from publications pages.

    No LLM usage; purely HTML parsing with domain-specific selectors.
    """
    link = _find_publications_link(profile_html, profile_url)
    if not link:
        logging.info("No publications link found for profile: %s", profile_url)
        return []

    logging.info("Checking publications page: %s", link)
    resp = await page.goto(link, wait_until="domcontentloaded", timeout=45000)
    if not resp or not (200 <= resp.status < 400):
        logging.warning("Failed to open publications list: %s", link)
        return []
    await page.wait_for_timeout(300)
    await _try_expand_abstract(page)
    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    # If the publications page itself is a DiVA record, extract directly
    low_link = link.lower()
    if ("diva-portal.org" in low_link) and ("record.jsf" in low_link) and ("pid=diva2:" in low_link):
        logging.info("Publications page is a DiVA record; extracting abstract directly")
        abstract_text = None
        # 1) dt/dd pattern
        for dt in soup.find_all('dt'):
            label = _t(dt.get_text(" ", strip=True)).lower()
            if "abstract" in label or "sammanfatt" in label:
                dd = dt.find_next_sibling('dd') or dt.find_next('dd')
                if dd:
                    abstract_text = _block_text(dd)
                    break
        # 2) common abstract containers by id/class
        if not abstract_text:
            el = soup.select_one('[id*="abstract"], [class*="abstract"]')
            if el:
                abstract_text = _block_text(el)
        # 3) meta tags carrying abstract/description
        if not abstract_text:
            meta = (
                soup.find('meta', attrs={'name': 'DC.Description'}) or
                soup.find('meta', attrs={'name': 'dc.description'}) or
                soup.find('meta', attrs={'name': 'dcterms.abstract'}) or
                soup.find('meta', attrs={'name': 'citation_abstract'}) or
                soup.find('meta', attrs={'name': 'description'})
            )
            if meta and meta.get('content'):
                abstract_text = _t(meta.get('content'))
        if abstract_text and _is_plausible_abstract(abstract_text):
            logging.info("Extracted abstract from DiVA page")
            return [abstract_text][:max_items]

    # Inline abstracts on the publications list page
    inline: List[str] = []
    for el in soup.select('[class*="abstract"], [id*="abstract"], [class*="sammanfatt"], [id*="sammanfatt"]'):
        text = _block_text(el)
        if _is_plausible_abstract(text):
            inline.append(text)
            if len(inline) >= max_items:
                break
    if not inline:
        np_txt = _heading_next_paragraph(soup)
        if np_txt:
            inline.append(np_txt)
    if inline:
        logging.info("Found %d inline abstracts on list page: %s", len(inline), link)
        return inline[:max_items]

    # Collect candidate links to individual publications; prioritize DiVA record pages
    anchors = soup.select("a[href]")
    seen: set[str] = set()
    diva_records: List[str] = []
    other_links: List[str] = []
    allow = re.compile(
        r"(doi\.org/|arxiv\.org/abs/|ieeexplore\.ieee\.org/document/|dl\.acm\.org/doi/|"
        r"link\.springer\.com/|springer\.com/|sciencedirect\.com/science/article/|"
        r"onlinelibrary\.wiley\.com/doi/|tandfonline\.com/doi/|nature\.com/|"
        r"scholar\.google\.com/|diva-portal\.org/|aclanthology\.org/|openreview\.net/|"
        r"neurips\.cc/|papers\.nips\.cc/|proceedings\.mlr\.press/|openaccess\.thecvf\.com/|"
        r"aaai\.org/|usenix\.org/|iclr\.cc/|icml\.cc/)"
    )
    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        url_abs = urljoin(link, href)
        # Skip obvious non-publication links (mailto, anchors)
        if url_abs.startswith("mailto:") or "#" in href:
            continue
        if url_abs in seen:
            continue
        seen.add(url_abs)
        u = url_abs.lower()
        # Explicitly prioritize DiVA record pages
        if ("diva-portal.org" in u) and ("record.jsf" in u) and ("pid=diva2:" in u):
            diva_records.append(url_abs)
            continue
        if allow.search(url_abs):
            other_links.append(url_abs)
    pub_links: List[str] = diva_records + other_links
    logging.info("Candidate publication links: %d (DiVA records: %d)", len(pub_links), len(diva_records))
    for i, u in enumerate(diva_records[:5]):
        logging.info("DiVARecord[%d]: %s", i, u)

    abstracts: List[str] = []
    for url in pub_links:
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            if not resp or not (200 <= resp.status < 400):
                continue
            await page.wait_for_timeout(200)
            await _try_expand_abstract(page)
            phtml = await page.content()
            psoup = BeautifulSoup(phtml, "html.parser")

            # Domain-specific selectors (check DiVA first)
            u = url.lower()
            abstract_text = None
            if "diva-portal.org" in u:
                logging.info("DiVA portal page matched: %s", url)
                # DiVA record pages often structure details in dl/dt/dd with label 'Abstract'
                # 1) dt/dd pattern
                for dt in psoup.find_all('dt'):
                    label = _t(dt.get_text(" ", strip=True)).lower()
                    if "abstract" in label or "sammanfatt" in label:
                        dd = dt.find_next_sibling('dd') or dt.find_next('dd')
                        if dd:
                            abstract_text = _block_text(dd)
                            break
                # 2) common abstract containers by id/class
                if not abstract_text:
                    el = psoup.select_one('[id*="abstract"], [class*="abstract"]')
                    if el:
                        abstract_text = _block_text(el)
                # 3) meta tags carrying abstract/description
                if not abstract_text:
                    meta = (
                        psoup.find('meta', attrs={'name': 'DC.Description'}) or
                        psoup.find('meta', attrs={'name': 'dc.description'}) or
                        psoup.find('meta', attrs={'name': 'dcterms.abstract'}) or
                        psoup.find('meta', attrs={'name': 'citation_abstract'}) or
                        psoup.find('meta', attrs={'name': 'description'})
                    )
                    if meta and meta.get('content'):
                        abstract_text = _t(meta.get('content'))
            elif "arxiv.org/abs/" in u:
                el = psoup.select_one('blockquote.abstract, meta[name="citation_abstract"]')
                abstract_text = _t(el.get("content") if el and el.name == 'meta' else (el.get_text(" ", strip=True) if el else ""))
            elif "ieeexplore.ieee.org/document/" in u:
                el = psoup.select_one('.abstract-text, meta[name="citation_abstract"]')
                abstract_text = _t(el.get("content") if el and el.name == 'meta' else (el.get_text(" ", strip=True) if el else ""))
            elif "dl.acm.org/doi/" in u:
                el = psoup.select_one('section.abstract, .abstractInFull')
                abstract_text = _block_text(el) if el else None
            elif "aclanthology.org" in u:
                el = psoup.select_one('section#abstract, div#abstract, p#abstract, div.abstract')
                if not el:
                    el = psoup.select_one('[id*="abstract"], [class*="abstract"]')
                abstract_text = _block_text(el) if el else None
                if not abstract_text:
                    meta = psoup.find('meta', attrs={'name': 'citation_abstract'}) or psoup.find('meta', attrs={'name': 'description'})
                    abstract_text = _t(meta.get('content')) if meta and meta.get('content') else None
            elif "openreview.net" in u:
                meta = psoup.find('meta', attrs={'name': 'citation_abstract'}) or psoup.find('meta', attrs={'name': 'description'})
                abstract_text = _t(meta.get('content')) if meta and meta.get('content') else None
                if not abstract_text:
                    el = psoup.select_one('[id*="abstract"], [class*="abstract"]')
                    abstract_text = _t(el.get_text(" ", strip=True)) if el else None
            elif "proceedings.mlr.press" in u:
                el = psoup.select_one('section#abstract, div#abstract, p#abstract')
                if not el:
                    el = psoup.select_one('[id*="abstract"], [class*="abstract"]')
                abstract_text = _t(el.get_text(" ", strip=True)) if el else None
            elif "openaccess.thecvf.com" in u:
                el = psoup.select_one('#abstract, div#abstract, section#abstract')
                if not el:
                    el = psoup.select_one('[id*="abstract"], [class*="abstract"]')
                abstract_text = _t(el.get_text(" ", strip=True)) if el else None
            elif ("neurips.cc" in u) or ("papers.nips.cc" in u) or ("aaai.org" in u) or ("usenix.org" in u) or ("iclr.cc" in u) or ("icml.cc" in u):
                el = psoup.select_one('section#abstract, div#abstract, p#abstract, .abstract, section.abstract')
                abstract_text = _t(el.get_text(" ", strip=True)) if el else None
                if not abstract_text:
                    meta = psoup.find('meta', attrs={'name': 'citation_abstract'}) or psoup.find('meta', attrs={'name': 'description'})
                    abstract_text = _t(meta.get('content')) if meta and meta.get('content') else None
            elif "springer" in u or "link.springer.com" in u:
                el = psoup.select_one('section#Abs1, section.Abstract')
                abstract_text = _t(el.get_text(" ", strip=True)) if el else None
            elif "sciencedirect.com" in u:
                el = psoup.select_one('div.Abstracts') or psoup.select_one('div.Abstracts p')
                abstract_text = _block_text(el) if el else None
            elif "wiley.com/doi/" in u:
                el = psoup.select_one('section.article-section__abstract, div.article-section__content')
                abstract_text = _block_text(el) if el else None
            elif "tandfonline.com/doi/" in u:
                el = psoup.select_one('div.abstractSection, section.abstract')
                abstract_text = _block_text(el) if el else None
            elif "nature.com" in u:
                el = psoup.select_one('div#Abs1-content, section#abstract')
                abstract_text = _block_text(el) if el else None
            elif "doi.org/" in u:
                # some DOIs redirect client-side; try meta
                meta = psoup.find("meta", attrs={"name": "dc.Description"}) or psoup.find("meta", attrs={"name": "description"})
                abstract_text = _t(meta.get("content")) if meta and meta.get("content") else None

            # Generic fallbacks
            if not abstract_text:
                np_txt = _heading_next_paragraph(psoup)
                if np_txt:
                    abstract_text = np_txt
            if not abstract_text:
                el = psoup.select_one('[class*="abstract"], [id*="abstract"], [class*="sammanfatt"], [id*="sammanfatt"]')
                if el:
                    abstract_text = _block_text(el)
            if not abstract_text:
                meta = psoup.find("meta", attrs={"name": "description"})
                if meta and meta.get("content"):
                    abstract_text = _t(meta["content"])

            if abstract_text and _is_plausible_abstract(abstract_text):
                abstracts.append(abstract_text)
            if len(abstracts) >= max_items:
                break
        except Exception as e:
            logging.exception("Error parsing publication %s: %s", url, e)
            continue

    return abstracts[:max_items]
