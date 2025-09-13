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


def _collect_abstracts(soup: BeautifulSoup, max_items: int = 3) -> List[str]:
    """Collect up to `max_items` plausible abstracts from a document.

    Priority:
    1) dt/dd labeled Abstract/Sammanfattning
    2) Containers with id/class containing 'abstract' or 'sammanfatt'
    3) Heading containing Abstract → next <p>
    """
    out: List[str] = []
    seen: set[str] = set()

    # 1) Definition lists
    for dt in soup.find_all('dt'):
        label = _t(dt.get_text(" ", strip=True)).lower()
        if "abstract" in label or "sammanfatt" in label:
            dd = dt.find_next_sibling('dd') or dt.find_next('dd')
            if dd:
                txt = _block_text(dd)
                if _is_plausible_abstract(txt):
                    norm = txt.strip()
                    if norm not in seen:
                        out.append(norm); seen.add(norm)
                        if len(out) >= max_items:
                            return out

    # 2) Common abstract containers
    for el in soup.select('[id*="abstract"], [class*="abstract"], [id*="sammanfatt"], [class*="sammanfatt"]'):
        txt = _block_text(el)
        if _is_plausible_abstract(txt):
            norm = txt.strip()
            if norm not in seen:
                out.append(norm); seen.add(norm)
                if len(out) >= max_items:
                    return out

    # 3) Heading followed by next paragraph
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        t = _t(h.get_text(" ", strip=True)).lower()
        if "abstract" in t or "sammanfattning" in t or "sammanfatt" in t or "summary" in t:
            p = h.find_next("p")
            if p:
                txt = _block_text(p)
                if _is_plausible_abstract(txt):
                    norm = txt.strip()
                    if norm not in seen:
                        out.append(norm); seen.add(norm)
                        if len(out) >= max_items:
                            return out

    return out


def _is_diva_record_url(url: str) -> bool:
    """Return True if URL looks like a DiVA record page link."""
    u = (url or "").lower()
    if "diva-portal.org" not in u:
        return False
    if "record.jsf" not in u:
        return False
    # pid can be encoded or not
    return bool(re.search(r"pid=diva2(?::|%3a|%253a)[0-9]+", u))


def _find_diva_links(soup: BeautifulSoup, base_url: str, html: str, max_items: int = 3) -> List[str]:
    """Find up to `max_items` DiVA record links in document order.

    Looks at href, data-href, onclick, and finally raw HTML regex fallback.
    """
    found: List[str] = []
    seen: set[str] = set()

    # Anchors first
    for a in soup.find_all("a"):
        href = a.get("href")
        if href:
            url_abs = urljoin(base_url, href)
            if _is_diva_record_url(url_abs) and url_abs not in seen:
                found.append(url_abs); seen.add(url_abs)
                if len(found) >= max_items:
                    return found
        dh = a.get("data-href")
        if dh:
            url_abs = urljoin(base_url, dh)
            if _is_diva_record_url(url_abs) and url_abs not in seen:
                found.append(url_abs); seen.add(url_abs)
                if len(found) >= max_items:
                    return found
        oc = a.get("onclick") or ""
        m = re.search(r"(https?://[^'\"\s]+diva-portal\.org[^'\"\s]*record\.jsf[^'\"\s]*)", oc, re.I)
        if m:
            url_abs = urljoin(base_url, m.group(1))
            if _is_diva_record_url(url_abs) and url_abs not in seen:
                found.append(url_abs); seen.add(url_abs)
                if len(found) >= max_items:
                    return found

    # Raw HTML fallback
    if html:
        for m in re.finditer(r"(https?://[^'\"\s<>]+diva-portal\.org[^'\"\s<>]*record\.jsf[^'\"\s<>)]*)", html, re.I):
            url_abs = m.group(1)
            if _is_diva_record_url(url_abs) and url_abs not in seen:
                found.append(url_abs); seen.add(url_abs)
                if len(found) >= max_items:
                    break

    return found


async def _safe_goto(page, url: str, timeout: int = 60000):
    resp = await page.goto(url, wait_until="load", timeout=timeout)
    try:
        await page.wait_for_load_state("networkidle", timeout=2000)
    except Exception:
        pass
    return resp


async def _safe_content(page, attempts: int = 3) -> str:
    last_err: Optional[Exception] = None
    for _ in range(attempts):
        try:
            return await page.content()
        except Exception as e:
            last_err = e
            try:
                await page.wait_for_load_state("load", timeout=2000)
            except Exception:
                pass
            await page.wait_for_timeout(200)
    # last try, re-raise if it still fails
    return await page.content()


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
        # Only consider KTH profile publications links, not external sites
        if not (abs_url.startswith("https://www.kth.se/") or abs_url.startswith("http://www.kth.se/") or abs_url.startswith("/")):
            continue
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
        parsed = urlparse(profile_url)
        base = _normalize_profile_base(profile_url)
        # Preserve ?l=en|sv when present
        lang_q = ""
        if parsed.query and "l=" in parsed.query:
            # keep only the l param
            m = re.search(r"\bl=([a-zA-Z]{2})\b", parsed.query)
            if m:
                lang_q = f"?l={m.group(1)}"
        fallback = f"{base}/publications{lang_q}"
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
    resp = await _safe_goto(page, link, timeout=60000)
    if not resp or not (200 <= resp.status < 400):
        logging.warning("Failed to open publications list: %s", link)
        return []
    await page.wait_for_timeout(300)
    await _try_expand_abstract(page)
    html = await _safe_content(page)
    soup = BeautifulSoup(html, "html.parser")
    pre_abstracts: List[str] = []

    # If the publications page itself is a DiVA record, extract directly
    low_link = link.lower()
    if ("diva-portal.org" in low_link) and ("record.jsf" in low_link) and ("pid=diva2:" in low_link):
        logging.info("Publications page is a DiVA record; extracting abstract(s) directly but continuing")
        di = _collect_abstracts(soup, max_items=max_items)
        if not di:
            meta = (
                soup.find('meta', attrs={'name': 'DC.Description'}) or
                soup.find('meta', attrs={'name': 'dc.description'}) or
                soup.find('meta', attrs={'name': 'dcterms.abstract'}) or
                soup.find('meta', attrs={'name': 'citation_abstract'}) or
                soup.find('meta', attrs={'name': 'description'})
            )
            if meta and meta.get('content') and _is_plausible_abstract(meta.get('content')):
                di = [_t(meta.get('content'))]
        pre_abstracts = di[:max_items]

    # Skip inline abstracts on list page; we will visit the first `max_items`
    # publication entries and extract one abstract per entry.

    # Find DiVA links anywhere on the publications page (document order)
    pub_links: List[str] = _find_diva_links(soup, link, html, max_items=max_items)
    logging.info("Selected first %d publication link(s) from list page", len(pub_links))
    if pub_links:
        logging.info("DiVA links on publications page: %s", ", ".join(pub_links))
    else:
        logging.info("DiVA links on publications page: none")

    abstracts: List[str] = []
    for url in pub_links:
        try:
            resp = await _safe_goto(page, url, timeout=60000)
            if not resp or not (200 <= resp.status < 400):
                continue
            await page.wait_for_timeout(200)
            await _try_expand_abstract(page)
            phtml = await _safe_content(page)
            psoup = BeautifulSoup(phtml, "html.parser")

            # Domain-specific selectors (check DiVA first) then generic collectors
            u = url.lower()
            page_abstracts: List[str] = []
            if "diva-portal.org" in u:
                logging.info("DiVA portal page matched: %s", url)
                page_abstracts = _collect_abstracts(psoup, max_items=max_items - len(abstracts))
                if not page_abstracts:
                    meta = (
                        psoup.find('meta', attrs={'name': 'DC.Description'}) or
                        psoup.find('meta', attrs={'name': 'dc.description'}) or
                        psoup.find('meta', attrs={'name': 'dcterms.abstract'}) or
                        psoup.find('meta', attrs={'name': 'citation_abstract'}) or
                        psoup.find('meta', attrs={'name': 'description'})
                    )
                    if meta and meta.get('content') and _is_plausible_abstract(meta.get('content')):
                        page_abstracts = [_t(meta.get('content'))]
            elif "arxiv.org/abs/" in u:
                el = psoup.select_one('blockquote.abstract, meta[name="citation_abstract"]')
                if el:
                    txt = _t(el.get("content") if el and el.name == 'meta' else el.get_text(" ", strip=True))
                    if _is_plausible_abstract(txt):
                        page_abstracts.append(txt)
            elif "ieeexplore.ieee.org/document/" in u:
                el = psoup.select_one('.abstract-text, meta[name="citation_abstract"]')
                if el:
                    txt = _t(el.get("content") if el and el.name == 'meta' else el.get_text(" ", strip=True))
                    if _is_plausible_abstract(txt):
                        page_abstracts.append(txt)
            elif "dl.acm.org/doi/" in u:
                el = psoup.select_one('section.abstract, .abstractInFull')
                if el:
                    txt = _block_text(el)
                    if _is_plausible_abstract(txt):
                        page_abstracts.append(txt)
            elif "aclanthology.org" in u:
                el = psoup.select_one('section#abstract, div#abstract, p#abstract, div.abstract') or psoup.select_one('[id*="abstract"], [class*="abstract"]')
                if el:
                    txt = _block_text(el)
                    if _is_plausible_abstract(txt):
                        page_abstracts.append(txt)
                if not page_abstracts:
                    meta = psoup.find('meta', attrs={'name': 'citation_abstract'}) or psoup.find('meta', attrs={'name': 'description'})
                    if meta and meta.get('content') and _is_plausible_abstract(meta.get('content')):
                        page_abstracts.append(_t(meta.get('content')))
            elif "openreview.net" in u:
                meta = psoup.find('meta', attrs={'name': 'citation_abstract'}) or psoup.find('meta', attrs={'name': 'description'})
                if meta and meta.get('content') and _is_plausible_abstract(meta.get('content')):
                    page_abstracts.append(_t(meta.get('content')))
                if not page_abstracts:
                    el = psoup.select_one('[id*="abstract"], [class*="abstract"]')
                    if el:
                        txt = _block_text(el)
                        if _is_plausible_abstract(txt):
                            page_abstracts.append(txt)
            elif "proceedings.mlr.press" in u:
                el = psoup.select_one('section#abstract, div#abstract, p#abstract') or psoup.select_one('[id*="abstract"], [class*="abstract"]')
                if el:
                    txt = _block_text(el)
                    if _is_plausible_abstract(txt):
                        page_abstracts.append(txt)
            elif "openaccess.thecvf.com" in u:
                el = psoup.select_one('#abstract, div#abstract, section#abstract') or psoup.select_one('[id*="abstract"], [class*="abstract"]')
                if el:
                    txt = _block_text(el)
                    if _is_plausible_abstract(txt):
                        page_abstracts.append(txt)
            elif ("neurips.cc" in u) or ("papers.nips.cc" in u) or ("aaai.org" in u) or ("usenix.org" in u) or ("iclr.cc" in u) or ("icml.cc" in u):
                el = psoup.select_one('section#abstract, div#abstract, p#abstract, .abstract, section.abstract')
                if el:
                    txt = _block_text(el)
                    if _is_plausible_abstract(txt):
                        page_abstracts.append(txt)
                if not page_abstracts:
                    meta = psoup.find('meta', attrs={'name': 'citation_abstract'}) or psoup.find('meta', attrs={'name': 'description'})
                    if meta and meta.get('content') and _is_plausible_abstract(meta.get('content')):
                        page_abstracts.append(_t(meta.get('content')))
            elif "springer" in u or "link.springer.com" in u:
                el = psoup.select_one('section#Abs1, section.Abstract')
                if el:
                    txt = _block_text(el)
                    if _is_plausible_abstract(txt):
                        page_abstracts.append(txt)
            elif "sciencedirect.com" in u:
                el = psoup.select_one('div.Abstracts') or psoup.select_one('div.Abstracts p')
                if el:
                    txt = _block_text(el)
                    if _is_plausible_abstract(txt):
                        page_abstracts.append(txt)
            elif "wiley.com/doi/" in u:
                el = psoup.select_one('section.article-section__abstract, div.article-section__content')
                if el:
                    txt = _block_text(el)
                    if _is_plausible_abstract(txt):
                        page_abstracts.append(txt)
            elif "tandfonline.com/doi/" in u:
                el = psoup.select_one('div.abstractSection, section.abstract')
                if el:
                    txt = _block_text(el)
                    if _is_plausible_abstract(txt):
                        page_abstracts.append(txt)
            elif "nature.com" in u:
                el = psoup.select_one('div#Abs1-content, section#abstract')
                if el:
                    txt = _block_text(el)
                    if _is_plausible_abstract(txt):
                        page_abstracts.append(txt)
            elif "doi.org/" in u:
                meta = psoup.find("meta", attrs={"name": "dc.Description"}) or psoup.find("meta", attrs={"name": "description"})
                if meta and meta.get("content") and _is_plausible_abstract(meta.get('content')):
                    page_abstracts.append(_t(meta.get('content')))

            # Generic collection if still empty
            if not page_abstracts:
                page_abstracts = _collect_abstracts(psoup, max_items=max_items - len(abstracts))
            if not page_abstracts:
                meta = psoup.find("meta", attrs={"name": "description"})
                if meta and meta.get("content") and _is_plausible_abstract(meta.get('content')):
                    page_abstracts = [_t(meta.get('content'))]

            if page_abstracts:
                abstracts.append(page_abstracts[0])
            if len(abstracts) >= max_items:
                break
        except Exception as e:
            logging.exception("Error parsing publication %s: %s", url, e)
            continue

    return abstracts[:max_items]
