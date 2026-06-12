# scrapers/opg/_base.py - OPG journal scraper

import re
import time
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class OPGBaseScraper(BaseScraper):
    """OPG journals: listing page (HTTP) → article detail pages (browser).

    Listing pages (issue.cfm / upcomingissue.cfm) work via HTTP.
    Article detail pages return 202 via HTTP (anti-bot), so browser
    mode is used to extract dates, abstracts, and full metadata.
    """

    journal_type = "opg"
    publisher = "Optica Publishing Group"

    def scrape(self):
        code = self.code
        url = self.list_url
        if not url:
            return [], None, None

        # Step 1: Fetch listing page (HTTP works for OPG listing pages)
        logger.info("[OPG:%s] Fetching listing: %s", code, url)
        html = self._fetch(url)
        if not html or len(html) < 5000:
            logger.warning("[OPG:%s] Failed to fetch listing page", code)
            return [], None, None

        # Step 2: Extract article URLs + vol/issue from listing
        urls, vol, iss = self._extract_listing_urls(html, code)

        # Step 3: Fetch detail pages for metadata
        if self.allow_browser:
            try:
                from DrissionPage import ChromiumPage  # noqa: F401
                articles = self._browser_fetch_details(urls, vol, iss)
            except ImportError:
                logger.info("[OPG:%s] DrissionPage not available, using listing data only", code)
                articles = self._parse_listing_fallback(html, code, vol, iss)
        else:
            articles = self._parse_listing_fallback(html, code, vol, iss)

        # Step 4: Fill missing abstracts via CrossRef API
        self._fetch_crossref_abstracts(articles)

        return articles, vol, iss

    # ── CrossRef abstract fetch ─────────────────────────────────────

    def _fetch_crossref_abstracts(self, articles):
        """Fetch abstracts from CrossRef API for articles missing them."""
        missing = [a for a in articles if a.get("doi") and not a.get("abstract", "")]
        if not missing:
            return
        logger.info("[OPG:%s] CrossRef: fetching %d abstracts...", self.code, len(missing))
        for art in missing:
            try:
                doi = art["doi"]
                resp = self._fetch(f"https://api.crossref.org/works/{doi}", timeout=10)
                if not resp:
                    continue
                data = __import__("json").loads(resp)
                abstract = data.get("message", {}).get("abstract", "")
                if abstract:
                    # Strip JATS XML tags: <jats:p>, </jats:p>, etc.
                    clean = re.sub(r"</?jats:[^>]+>", "", abstract)
                    clean = re.sub(r"<[^>]+>", " ", clean)
                    clean = re.sub(r"\s+", " ", clean).strip()
                    if len(clean) > 50:
                        art["abstract"] = clean[:5000]
                        art["abstract_cn"] = ""
            except Exception:
                logger.exception("[OPG:%s] CrossRef error for %s", self.code, art.get("doi", "?"))

    # ── Listing page extraction ─────────────────────────────────────

    def _extract_listing_urls(self, html, code):
        """Extract article URLs/DOIs and vol/issue from listing page."""
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        seen_uris = set()

        # Volume/issue
        vol, iss = self._extract_vol_iss_from_page(soup, html)

        # Article links
        title_elems = soup.select("p.article-title a")
        if not title_elems:
            title_elems = [
                a for a in soup.find_all("a", href=True)
                if "abstract.cfm?uri=" in a.get("href", "")
            ]

        logger.info("[OPG:%s] Found %d article links", code, len(title_elems))

        for a in title_elems:
            href = a.get("href", "")
            title = self._clean(a.get_text())
            if not title or len(title) < 5:
                continue

            uri_match = re.search(r"uri=([a-zA-Z0-9\-\.]+)", href)
            uri = uri_match.group(1) if uri_match else ""
            if uri in seen_uris:
                continue
            seen_uris.add(uri)

            if href.startswith("/"):
                full_url = f"https://opg.optica.org{href}"
            elif href.startswith("http"):
                full_url = href
            else:
                full_url = f"https://opg.optica.org/{href}"

            # Authors from listing page (fallback)
            authors = ""
            parent = a.parent
            for _ in range(5):
                if parent and parent.name in ("div", "li", "article", "section", "p"):
                    break
                parent = parent.parent if parent else None
            if parent:
                auth_elem = parent.find_next("p", class_="article-authors")
                if auth_elem:
                    authors = self._clean(auth_elem.get_text())

            # Date from listing page ("Published on: MM/DD/YYYY")
            listing_date = ""
            if parent:
                date_elem = parent.find_next("p", class_="article-location")
                if date_elem:
                    date_text = self._clean(date_elem.get_text())
                    dm = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_text)
                    if dm:
                        listing_date = f"{dm.group(3)}-{dm.group(1).zfill(2)}-{dm.group(2).zfill(2)}"

            urls.append({
                "url": full_url,
                "uri": uri,
                "listing_title": title,
                "listing_authors": authors,
                "listing_date": listing_date,
                "doi": f"10.1364/{uri}" if uri else "",
            })

        # If page-level vol/iss failed, try URI
        if (not vol or not iss) and urls:
            parsed_vol, parsed_iss = self._parse_vol_iss_from_uri(urls[0]["uri"], code)
            if not vol:
                vol = parsed_vol
            if not iss:
                iss = parsed_iss

        logger.info("[OPG:%s] Listing: %d URLs, Vol %s Iss %s", code, len(urls), vol, iss)
        return urls, vol, iss

    # ── Browser mode ─────────────────────────────────────────────────

    def _browser_fetch_details(self, urls, vol, iss):
        """Visit each article detail page with browser for full metadata.

        If self.browser_address is set (e.g. "127.0.0.1:9222"), connects to
        an existing Chrome started with --remote-debugging-port=9222.
        Otherwise launches a new browser instance.
        """
        from DrissionPage import ChromiumPage, ChromiumOptions

        co = ChromiumOptions()
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_argument('--lang=en-US')
        co.set_argument('--disable-features=TranslateUI')
        co.set_load_mode('eager')       # wait for DOMContentLoaded, not all resources
        co.set_timeouts(page_load=15)   # 15s timeout per page navigation

        browser_addr = getattr(self, 'browser_address', '')
        if browser_addr:
            co.set_address(browser_addr)
            logger.info("[OPG:%s] Connecting to existing browser at %s", self.code, browser_addr)

        page = ChromiumPage(co)
        articles = []
        today = datetime.now().strftime("%Y-%m-%d")
        skip_urls = getattr(self, 'skip_urls', set())

        try:
            for i, entry in enumerate(urls):
                url = entry["url"]

                # ── Skip if already has abstract in DB ──────────────────
                if url in skip_urls:
                    logger.debug("[OPG:%s] Skip (has abstract): %s", self.code, url[:80])
                    # Minimal entry — save_articles will skip update since
                    # abstract/authors/pub_date are empty (won't overwrite DB data)
                    articles.append({
                        "title": entry["listing_title"],
                        "title_cn": "",
                        "authors": "",
                        "url": url,
                        "doi": "",
                        "pub_date": "",
                        "journal_ref": "",
                        "volume": str(vol) if vol else None,
                        "issue": str(iss) if iss else None,
                        "abstract": "",
                        "abstract_cn": "",
                    })
                    if self._on_progress:
                        self._on_progress(i + 1)
                    continue
                try:
                    # ── Load page with CAPTCHA-aware wait ────────────────────
                    CAPTCHA_MARKER = "enter the letters and/or numbers below"

                    def _wait_for_captcha_solve():
                        """Poll browser until user manually solves the CAPTCHA."""
                        logger.warning(
                            "[OPG:%s] [!] CAPTCHA on %s — solve it in the browser window",
                            self.code, url,
                        )
                        for attempt in range(300):  # ~5 min timeout
                            time.sleep(1)
                            html_text = page.html
                            if CAPTCHA_MARKER not in html_text and len(html_text) > 5000:
                                logger.info("[OPG:%s] CAPTCHA solved after ~%ds", self.code, attempt)
                                return
                        raise TimeoutError("CAPTCHA solve timeout")

                    page.get(url)
                    # Wait for page to settle, polling for CAPTCHA
                    for _ in range(30):
                        time.sleep(1)
                        html_text = page.html
                        if CAPTCHA_MARKER in html_text:
                            _wait_for_captcha_solve()
                            break
                        if len(html_text) > 20000:
                            break

                    soup = BeautifulSoup(page.html, "html.parser")

                    # Collect citation_* meta tags
                    meta = {}
                    for m in soup.find_all("meta"):
                        name = m.get("name", "")
                        if name.startswith("citation_"):
                            meta[name] = m.get("content", "")

                    # Title
                    title = meta.get("citation_title", "")
                    if not title:
                        title = entry["listing_title"]

                    # Authors from meta (deduplicate consecutive duplicates from multiple affiliations)
                    author_names = []
                    for m in soup.find_all("meta"):
                        if m.get("name") == "citation_author":
                            name = m.get("content", "").strip()
                            if name and (not author_names or author_names[-1] != name):
                                author_names.append(name)
                    authors = ", ".join(author_names)
                    if not authors:
                        authors = entry.get("listing_authors", "")

                    # Pub date: citation_online_date (First Published)
                    pub_date = meta.get("citation_online_date", "").replace("/", "-")[:10]
                    if not pub_date:
                        pub_date = meta.get("citation_publication_date", "").replace("/", "-")[:10]
                    if not pub_date:
                        pub_date = entry.get("listing_date", "") or today

                    # DOI
                    doi = meta.get("citation_doi", "") or entry["doi"]

                    # Abstract — use citation_abstract from meta if available
                    abstract = meta.get("citation_abstract", "")
                    if not abstract:
                        # Fallback: find "Abstract" heading and take next sibling
                        abs_heading = soup.find(
                            lambda tag: tag.name in ("h2", "h3", "h4")
                            and tag.get_text(strip=True).lower() == "abstract"
                        )
                        if abs_heading:
                            abs_el = abs_heading.find_next_sibling("div")
                            if abs_el:
                                abs_text = self._clean(abs_el.get_text())
                                if len(abs_text) > 50:
                                    abstract = abs_text[:5000]

                    # Volume/issue from meta (more reliable)
                    article_vol = meta.get("citation_volume", "") or str(vol) if vol else None
                    article_iss = meta.get("citation_issue", "") or str(iss) if iss else None

                    journal_ref = f"{self.journal_name} Vol.{article_vol}"
                    if article_iss:
                        journal_ref += f", Issue {article_iss}"

                    articles.append({
                        "title": title,
                        "title_cn": "",
                        "authors": authors,
                        "url": url,
                        "doi": doi,
                        "pub_date": pub_date,
                        "journal_ref": journal_ref,
                        "volume": str(article_vol) if article_vol else None,
                        "issue": str(article_iss) if article_iss else None,
                        "abstract": abstract,
                        "abstract_cn": "",
                    })

                    if self._on_progress:
                        self._on_progress(i + 1)

                except Exception:
                    logger.exception("[OPG:%s] Detail fetch error: %s", self.code, url)
                    articles.append({
                        "title": entry["listing_title"],
                        "title_cn": "",
                        "authors": entry.get("listing_authors", ""),
                        "url": url,
                        "doi": entry["doi"],
                        "pub_date": entry.get("listing_date", "") or today,
                        "journal_ref": "",
                        "volume": str(vol) if vol else None,
                        "issue": str(iss) if iss else None,
                        "abstract": "",
                        "abstract_cn": "",
                    })

        finally:
            try:
                if not browser_addr:
                    page.quit()
            except Exception:
                pass

        logger.info("[OPG:%s] %d articles extracted from detail pages", self.code, len(articles))
        return articles

    # ── HTTP fallback (listing data only) ────────────────────────────

    def _parse_listing_fallback(self, html, code, vol, iss):
        """Parse articles from listing page only (no abstracts, approximate dates)."""
        soup = BeautifulSoup(html, "html.parser")
        articles = []

        title_elems = soup.select("p.article-title a")
        if not title_elems:
            title_elems = [
                a for a in soup.find_all("a", href=True)
                if "abstract.cfm?uri=" in a.get("href", "")
            ]

        for a in title_elems:
            href = a.get("href", "")
            title = self._clean(a.get_text())
            if not title or len(title) < 5:
                continue

            uri_match = re.search(r"uri=([a-zA-Z0-9\-\.]+)", href)
            uri = uri_match.group(1) if uri_match else ""

            if href.startswith("/"):
                full_url = f"https://opg.optica.org{href}"
            else:
                full_url = href if href.startswith("http") else f"https://opg.optica.org/{href}"

            # Authors
            authors = ""
            parent = a.parent
            for _ in range(5):
                if parent and parent.name in ("div", "li", "article", "section", "p"):
                    break
                parent = parent.parent if parent else None
            if parent:
                auth_elem = parent.find_next("p", class_="article-authors")
                if auth_elem:
                    authors = self._clean(auth_elem.get_text())

            pub_date = datetime.now().strftime("%Y-%m-%d")
            # Try to extract date from listing page ("Published on: MM/DD/YYYY")
            if parent:
                date_elem = parent.find_next("p", class_="article-location")
                if date_elem:
                    date_text = self._clean(date_elem.get_text())
                    dm = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_text)
                    if dm:
                        pub_date = f"{dm.group(3)}-{dm.group(1).zfill(2)}-{dm.group(2).zfill(2)}"

            articles.append({
                "title": title, "title_cn": "",
                "authors": authors, "url": full_url,
                "doi": f"10.1364/{uri}" if uri else "",
                "pub_date": pub_date,
                "journal_ref": f"Vol.{vol}" + (f" Iss.{iss}" if iss else "") if vol else "",
                "volume": str(vol) if vol else None,
                "issue": str(iss) if iss else None,
                "abstract": "", "abstract_cn": "",
            })
            if self._on_progress:
                self._on_progress(len(articles))

        return articles

    # ── Volume/issue helpers ─────────────────────────────────────────

    def _extract_vol_iss_from_page(self, soup, html):
        vol, iss = None, None
        title_tag = soup.find("title")
        page_title = title_tag.get_text() if title_tag else html[:2000]
        if page_title:
            vol = self._extract_volume(page_title)
            iss = self._extract_issue(page_title)
        if not vol:
            vol = self._extract_meta(html, "citation_volume")
        if not iss:
            iss = self._extract_meta(html, "citation_issue")
        if not vol or not iss:
            for h in soup.find_all(["h1", "h2", "h3"]):
                h_text = self._clean(h.get_text())
                if not vol:
                    vol = self._extract_volume(h_text)
                if not iss:
                    iss = self._extract_issue(h_text)
                if vol and iss:
                    break
        return vol, iss

    def _parse_vol_iss_from_uri(self, uri, code):
        vol, iss = None, None
        uri_rest = uri[len(code) + 1:] if uri.startswith(code + "-") else uri
        parts = uri_rest.split("-")
        if len(parts) >= 2:
            for i, p in enumerate(parts):
                if p.isdigit() and len(p) <= 3:
                    if vol is None:
                        vol = p
                    elif iss is None:
                        iss = p
                        break
        return vol, iss
