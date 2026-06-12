# scrapers/ieee/_base.py - IEEE Xplore scraper (REST API + detail page)

import re
import json
import time
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# IEEE internal REST API (no API key needed)
IEEE_SEARCH_URL = "https://ieeexplore.ieee.org/rest/search"


class IEEEXploreScraper(BaseScraper):
    """IEEE Xplore journals: POST to /rest/search for article list,
    then GET /document/{id} for full abstracts via JS metadata.

    No browser needed — pure HTTP requests.
    """

    journal_type = "ieee"
    publisher = "IEEE"
    punumber: str = ""  # IEEE publication number

    def scrape(self):
        code = self.code
        punum = self.punumber
        if not punum:
            logger.warning("[IEEE:%s] No punumber configured", code)
            return [], None, None

        today = datetime.now().strftime("%Y-%m-%d")
        articles = []
        seen_dois = set()
        vol = iss = None

        # Search for this journal's recent articles
        search_body = {
            "newsearch": True,
            "queryText": self.journal_name,
            "rowsPerPage": 100,
            "pageNumber": 1,
            "returnType": "SEARCH",
            "highlight": True,
            "returnFacets": ["ALL"],
            "sortType": "newest",
        }

        logger.info("[IEEE:%s] POST search — pub# %s", code, punum)
        html = self._post_json(IEEE_SEARCH_URL, search_body)
        if not html:
            return [], None, None

        try:
            data = json.loads(html)
        except json.JSONDecodeError:
            logger.warning("[IEEE:%s] Invalid JSON from search API", code)
            return [], None, None

        records = data.get("records", [])
        total = data.get("totalRecords", len(records))
        logger.info("[IEEE:%s] %d records (total: %s)", code, len(records), total)

        for item in records:
            try:
                # Only include articles from this journal's publication number
                if str(item.get("publicationNumber", "")) != str(punum):
                    continue

                title = self._clean(item.get("articleTitle", ""))
                if not title or len(title) < 10:
                    continue

                doi = item.get("doi", "")
                if doi in seen_dois:
                    continue
                seen_dois.add(doi)

                # Authors: list of {"preferredName": "..."}
                authors_list = item.get("authors", [])
                if isinstance(authors_list, list):
                    authors = ", ".join(
                        a.get("preferredName", a.get("name", ""))
                        for a in authors_list
                        if a.get("preferredName") or a.get("name")
                    )
                else:
                    authors = ""

                # Date: search results only have publicationYear; detail page has full date
                pub_year = item.get("publicationYear", "")
                pub_date = f"{pub_year}-01-01" if pub_year else today

                # Volume / Issue (skip "PP" = early access placeholder)
                e_vol = item.get("volume") or None
                e_iss = item.get("issue") or None
                if e_vol and e_vol not in ("PP", "99", ""):
                    vol = vol or str(e_vol)
                    e_vol = str(e_vol)
                else:
                    e_vol = None
                if e_iss and e_iss not in ("99", ""):
                    iss = iss or str(e_iss)
                    e_iss = str(e_iss)
                else:
                    e_iss = None

                # Abstract (may be truncated in search results — detail page has full)
                abstract = ""
                raw = item.get("abstract", "")
                if raw:
                    clean = re.sub(r"<[^>]+>", " ", raw)
                    clean = re.sub(r"\s+", " ", clean).strip()
                    if len(clean) > 50:
                        abstract = clean[:5000]

                # Article URL
                article_num = item.get("articleNumber", "")
                if article_num:
                    article_url = f"https://ieeexplore.ieee.org/document/{article_num}"
                else:
                    article_url = f"https://ieeexplore.ieee.org/document/{doi}" if doi else ""

                # Journal name
                pub_title = item.get("publicationTitle", self.journal_name)

                articles.append({
                    "title": title,
                    "title_cn": "",
                    "authors": authors,
                    "url": article_url,
                    "doi": doi,
                    "pub_date": pub_date,
                    "journal_ref": pub_title,
                    "abstract": abstract,
                    "abstract_cn": "",
                    "volume": str(e_vol) if e_vol else None,
                    "issue": str(e_iss) if e_iss else None,
                })
                if self._on_progress:
                    self._on_progress(len(articles))

            except Exception:
                logger.exception("[IEEE:%s] Parse error for record", code)

        # Fetch full abstracts from detail pages (search results give truncated abstracts)
        self._fetch_full_abstracts(articles)

        logger.info("[IEEE:%s] %d articles, Vol %s Iss %s", code, len(articles), vol, iss)
        return articles, vol, iss

    # ── Detail page: extract xplGlobal.document.metadata ──────────────

    def _fetch_full_abstracts(self, articles):
        """Visit article detail pages to extract full abstract + metadata
        from the xplGlobal.document.metadata JavaScript variable."""
        missing = [a for a in articles if not a.get("abstract") or len(a.get("abstract", "")) < 100]
        if not missing:
            return
        logger.info("[IEEE:%s] Fetching %d full abstracts from detail pages...", self.code, len(missing))

        for art in missing:
            try:
                url = art["url"]
                if not url:
                    continue

                html = self._get_html(url)
                if not html:
                    continue

                # Extract xplGlobal.document.metadata=...;
                metadata = self._extract_metadata(html)
                if not metadata:
                    continue

                # Full abstract
                abstract = metadata.get("abstract", "")
                if abstract:
                    clean = re.sub(r"<[^>]+>", " ", abstract)
                    clean = re.sub(r"\s+", " ", clean).strip()
                    if len(clean) > 50:
                        art["abstract"] = clean[:5000]

                # More precise date (format: "08 June 2026")
                for key in ("dateOfInsertion", "publicationDate", "onlineDate"):
                    d = metadata.get(key, "")
                    if d and len(d) >= 8:
                        try:
                            art["pub_date"] = datetime.strptime(d.strip(), "%d %B %Y").strftime("%Y-%m-%d")
                        except ValueError:
                            try:
                                art["pub_date"] = datetime.strptime(d.strip()[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
                            except ValueError:
                                pass
                        break

                # Better DOI
                doi = metadata.get("doi", "")
                if doi and not art["doi"]:
                    art["doi"] = doi

                # Better volume/issue
                if not art["volume"]:
                    v = metadata.get("volume", "")
                    if v:
                        art["volume"] = str(v)
                if not art["issue"]:
                    iss = metadata.get("issue", "")
                    if iss:
                        art["issue"] = str(iss)

                # Better title
                md_title = metadata.get("title", "") or metadata.get("formulaStrippedArticleTitle", "")
                if md_title and len(md_title) > len(art.get("title", "")):
                    art["title"] = self._clean(md_title)

                # Better authors
                md_authors = metadata.get("authors", [])
                if isinstance(md_authors, list) and md_authors:
                    author_names = []
                    for a in md_authors:
                        name = a.get("name", "") or a.get("authorName", "")
                        if name:
                            author_names.append(name)
                    if author_names:
                        art["authors"] = ", ".join(author_names)

            except Exception:
                logger.exception("[IEEE:%s] Detail fetch error for %s", self.code, art.get("url", "?"))

    def _extract_metadata(self, html):
        """Extract xplGlobal.document.metadata JSON from article detail page."""
        match = re.search(
            r"xplGlobal\.document\.metadata\s*=\s*(\{.+?\})\s*;",
            html, re.MULTILINE | re.DOTALL,
        )
        if not match:
            # Try alternate patterns
            match = re.search(
                r"metadata\s*[:=]\s*(\{.+?\})\s*;",
                html, re.MULTILINE | re.DOTALL,
            )
            if not match:
                return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    # ── HTTP helpers ─────────────────────────────────────────────────

    def _post_json(self, url, body, timeout=20):
        """POST JSON to IEEE API."""
        import requests as _requests
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Referer": "https://ieeexplore.ieee.org/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        }
        for attempt in range(4):
            try:
                r = _requests.post(url, data=json.dumps(body), headers=headers, timeout=timeout)
                if r.status_code == 403:
                    logger.error("[IEEE:%s] 403 Forbidden from %s", self.code, url)
                    return None
                if r.status_code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.text
            except Exception:
                if attempt < 3:
                    time.sleep(2)
                else:
                    logger.warning("[IEEE:%s] POST failed after 4 attempts: %s", self.code, url)
                    return None
        return None

    def _get_html(self, url, timeout=15):
        """GET an IEEE page and return HTML text."""
        import requests as _requests
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://ieeexplore.ieee.org/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        }
        for attempt in range(4):
            try:
                r = _requests.get(url, headers=headers, timeout=timeout)
                if r.status_code == 403:
                    return None
                if r.status_code == 429:
                    time.sleep(5 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.text
            except Exception:
                if attempt < 3:
                    time.sleep(2)
                else:
                    return None
        return None


# ═══════════════════════════════════════════════════════════════════
# Shared DrissionPage-based scraper (used by tmtt, mwtl, tap, thz, awpl, microwave_mag)
# ═══════════════════════════════════════════════════════════════════

def ieee_browser_scrape(self):
    """Generic IEEE scraper: REST API → rendered TOC → detail pages."""
    if not self.allow_browser:
        logger.warning("[%s] Browser required", self.code.upper())
        return [], None, None

    from DrissionPage import ChromiumPage, ChromiumOptions
    from bs4 import BeautifulSoup

    co = ChromiumOptions()
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_timeouts(page_load=30)

    browser_addr = getattr(self, "browser_address", "")
    if browser_addr:
        co.set_address(browser_addr)

    page = ChromiumPage(co)
    articles, vol, iss = [], None, None
    skip_urls = getattr(self, "skip_urls", set())
    punum = self.punumber

    try:
        # ── Step 1: Open journal home first (establishes session) ──
        page.get(f"https://ieeexplore.ieee.org/xpl/mostRecentIssue.jsp?punumber={punum}")
        page.wait.doc_loaded()
        time.sleep(1)

        # ── Step 2: Issues API via browser ─────────────────────────
        page.get(f"https://ieeexplore.ieee.org/rest/publication/{punum}/issues")
        for _ in range(10):
            time.sleep(0.5)
            try:
                if len(page.html) > 200:
                    break
            except Exception:
                continue

        raw = page.html
        pre_m = re.search(r"<pre>(.*?)</pre>", raw, re.DOTALL)
        issues = json.loads(pre_m.group(1) if pre_m else raw)
        latest = issues[0]
        vol = str(latest.get("volume", ""))
        iss = str(latest.get("issue", ""))
        isnumber = str(latest.get("issueNumber", ""))
        logger.info("[%s] V%s I%s (isnumber=%s)", self.code.upper(), vol, iss, isnumber)

        # ── Step 2: TOC page ───────────────────────────────────────
        toc_url = (
            f"https://ieeexplore.ieee.org/xpl/tocresult.jsp"
            f"?isnumber={isnumber}&punumber={punum}"
        )
        logger.info("[%s] Opening TOC", self.code.upper())
        page.get(toc_url)
        page.wait.doc_loaded()

        html = ""
        for _ in range(15):
            time.sleep(1)
            try:
                html = page.html
            except Exception:
                continue
            if len(re.findall(r'/document/(\d+)', html)) > 10 and len(html) > 80000:
                break

        soup = BeautifulSoup(html, "html.parser")

        # ── Step 3: Extract article links ──────────────────────────
        seen = set()
        entries = []
        for a in soup.find_all("a", href=re.compile(r"/document/(\d+)")):
            art_num = re.search(r"/document/(\d+)", a["href"]).group(1)
            if art_num in seen:
                continue
            seen.add(art_num)
            title = self._clean(a.get_text())
            if len(title) < 10:
                p = a.parent
                for _ in range(6):
                    if p is None:
                        break
                    h = p.find(["h2", "h3", "h4"])
                    if h:
                        title = self._clean(h.get_text())
                        if len(title) >= 10:
                            break
                    p = p.parent
            if len(title) < 10:
                continue
            entries.append({
                "title": title,
                "url": f"https://ieeexplore.ieee.org/document/{art_num}",
            })

        logger.info("[%s] Found %d articles in TOC", self.code.upper(), len(entries))

        # ── Step 4: Detail pages ───────────────────────────────────
        today = datetime.now().strftime("%Y-%m-%d")
        for i, entry in enumerate(entries):
            url = entry["url"]
            if url in skip_urls:
                articles.append(_make_article(entry["title"], "", url, today, vol, iss))
                if self._on_progress:
                    self._on_progress(i + 1)
                continue

            if self._on_progress:
                self._on_progress({"step": "抓取详情", "count": i + 1})

            try:
                page.get(url)
                detail_html = ""
                for _ in range(15):
                    time.sleep(0.3)
                    try:
                        detail_html = page.html
                    except Exception:
                        continue
                    if "xplGlobal.document.metadata" in detail_html:
                        break

                meta = _extract_ieee_metadata(detail_html)
                pub_date, abstract, authors, title, doi = (
                    today, "", "", entry["title"], ""
                )

                if meta:
                    for key in ("displayPublicationDate", "dateOfInsertion", "onlineDate"):
                        d = meta.get(key, "").strip()
                        if d:
                            for fmt in ("%d %B %Y", "%Y-%m-%d", "%B %Y"):
                                for attempt in (d, d.split("-")[-1].strip(), d[:10]):
                                    try:
                                        pub_date = datetime.strptime(
                                            attempt, fmt
                                        ).strftime("%Y-%m-%d")
                                        break
                                    except ValueError:
                                        continue
                                if pub_date != today:
                                    break

                    raw_abs = meta.get("abstract", "")
                    if raw_abs:
                        clean = re.sub(r"<[^>]+>", " ", raw_abs)
                        clean = re.sub(r"\s+", " ", clean).strip()
                        if len(clean) > 50:
                            abstract = clean[:5000]

                    md_t = meta.get("title") or meta.get(
                        "formulaStrippedArticleTitle", ""
                    )
                    if md_t and len(md_t) > len(title):
                        title = self._clean(md_t)

                    md_a = meta.get("authors", [])
                    if isinstance(md_a, list) and md_a:
                        names = [
                            a.get("name") or a.get("authorName", "")
                            for a in md_a
                        ]
                        names = [n for n in names if n]
                        if names:
                            authors = ", ".join(names)

                    md_doi = meta.get("doi", "")
                    if md_doi:
                        doi = md_doi

                articles.append(_make_article(
                    title, authors, url, pub_date, vol, iss,
                    abstract=abstract, doi=doi,
                ))

            except Exception:
                logger.exception("[%s] Detail error: %s", self.code.upper(), url)
                articles.append(_make_article(
                    entry["title"], "", url, today, vol, iss,
                ))

    finally:
        try:
            if not browser_addr:
                page.quit()
        except Exception:
            pass

    logger.info("[%s] Done: %d articles, Vol %s Iss %s",
                self.code.upper(), len(articles), vol, iss)
    return articles, vol, iss


def _make_article(title, authors, url, pub_date, vol, iss, abstract="", doi=""):
    return {
        "title": title, "title_cn": "",
        "authors": authors, "url": url, "doi": doi,
        "pub_date": pub_date,
        "journal_ref": f"Vol.{vol}" + (f" Iss.{iss}" if iss else ""),
        "abstract": abstract, "abstract_cn": "",
        "volume": str(vol) if vol else None,
        "issue": str(iss) if iss else None,
    }


def _extract_ieee_metadata(html):
    m = re.search(
        r"xplGlobal\.document\.metadata\s*=\s*(\{.+?\})\s*;",
        html, re.DOTALL,
    )
    if not m:
        m = re.search(r"metadata\s*[:=]\s*(\{.+?\})\s*;", html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
