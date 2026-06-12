# scrapers/nature/_base.py - Nature journal scraper

import re
import time
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class NatureBaseScraper(BaseScraper):
    """Nature journals: listing page → article detail pages via HTTP.

    Volume mode (nphoton):
        volumes → latest volume → latest issue → article URLs → detail pages.

    Direct listing mode (lsa, ncomms):
        list_url (2 pages) → article URLs → detail pages.

    All metadata (title, authors, abstract, date, DOI, vol/issue)
    comes from precise citation_* meta tags on the detail pages.
    """

    journal_type = "nature"
    publisher = "Nature Publishing Group"
    nature_code = ""
    use_volume_navigation = True

    def scrape(self):
        code = self.nature_code
        if self.use_volume_navigation:
            return self._scrape_volume_navigation(code)
        else:
            return self._scrape_direct_listing(code)

    # ── Volume navigation mode (nphoton) ────────────────────────────

    def _scrape_volume_navigation(self, code):
        # Step 1: Find latest volume
        logger.info("[Nature:%s] Step 1: Finding latest volume", code)
        html = self._fetch(self.list_url)
        if not html:
            logger.warning("[Nature:%s] Cannot access volumes page", code)
            return [], None, None

        vol_links = re.findall(rf"/{code}/volumes/(\d+)", html)
        if not vol_links:
            vol_links = re.findall(r"/volumes/(\d+)", html)
        if not vol_links:
            logger.warning("[Nature:%s] No volume links found", code)
            return [], None, None

        latest_vol = str(max(int(v) for v in vol_links))
        logger.info("[Nature:%s] Latest volume: %s", code, latest_vol)
        if self._on_progress:
            self._on_progress({"step": f"找到最新卷 Vol.{latest_vol}，查找最新期..."})

        # Step 2: Find latest issue
        vol_page_url = f"https://www.nature.com/{code}/volumes/{latest_vol}"
        html = self._fetch(vol_page_url)
        if not html:
            return self._try_direct_issue(code, latest_vol)

        issue_links = re.findall(rf"/{code}/volumes/{latest_vol}/issues/(\d+)", html)
        if not issue_links:
            issue_links = re.findall(rf"/volumes/{latest_vol}/issues/(\d+)", html)
        if not issue_links:
            return self._try_direct_issue(code, latest_vol)

        latest_issue = str(max(int(v) for v in issue_links))
        logger.info("[Nature:%s] Latest issue: %s", code, latest_issue)
        if self._on_progress:
            self._on_progress({"step": f"Vol.{latest_vol} Issue {latest_issue}，正在提取文章链接..."})

        # Step 3: Extract article URLs from issue page
        issue_url = f"https://www.nature.com/{code}/volumes/{latest_vol}/issues/{latest_issue}"
        html = self._fetch(issue_url)
        if not html or len(html) < 5000:
            logger.warning("[Nature:%s] Issue page failed", code)
            return [], latest_vol, latest_issue

        urls = self._extract_listing_urls(html, code)
        articles = self._fetch_detail_pages(code, urls, latest_vol, latest_issue)
        return articles, latest_vol, latest_issue

    def _try_direct_issue(self, code, vol):
        """Fallback: try common issue numbers."""
        for issue_num in range(12, 0, -1):
            url = f"https://www.nature.com/{code}/volumes/{vol}/issues/{issue_num}"
            html = self._fetch(url, timeout=10)
            if html and len(html) > 10000:
                logger.info("[Nature:%s] Found issue %s via direct search", code, issue_num)
                urls = self._extract_listing_urls(html, code)
                articles = self._fetch_detail_pages(code, urls, vol, str(issue_num))
                return articles, vol, str(issue_num)
        logger.warning("[Nature:%s] Could not find any valid issue page", code)
        return [], vol, None

    # ── Direct listing mode (lsa, ncomms) ───────────────────────────

    def _scrape_direct_listing(self, code):
        """Scrape articles from list_url, first 2 pages."""
        all_urls = []
        seen = set()
        next_url = self.list_url

        for page_num in range(1, 10):  # up to 9 pages (auto-breaks when no next link)
            logger.info("[Nature:%s] Fetching page %d: %s", code, page_num, next_url)
            html = self._fetch(next_url)
            if not html or len(html) < 5000:
                logger.warning("[Nature:%s] Failed to fetch page %d", code, page_num)
                break

            urls = self._extract_listing_urls(html, code)
            for u in urls:
                if u["url"] not in seen:
                    seen.add(u["url"])
                    all_urls.append(u)
            if self._on_progress:
                self._on_progress({"step": f"第{page_num}页，已找到", "count": len(all_urls)})

            # Find next page link
            soup = BeautifulSoup(html, "html.parser")
            next_link = soup.select_one(f'.c-pagination a[href*="page={page_num + 1}"]')
            if not next_link:
                break
            href = next_link.get("href", "")
            next_url = f"https://www.nature.com{href}" if href.startswith("/") else href

        articles = self._fetch_detail_pages(code, all_urls, None, None)
        return articles, None, None

    # ── Listing page URL extraction ─────────────────────────────────

    def _extract_listing_urls(self, html, code):
        """Extract article URLs from listing/issue page. Precise selectors only."""
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        seen = set()

        for article_elem in soup.find_all("article"):
            # Try standard listing page selector, then subjects page selector
            link = (
                article_elem.select_one('h3.c-card__title a[itemprop="url"]')
                or article_elem.select_one('h3 a[href*="/articles/"]')
                or article_elem.select_one('h2 a[href*="/articles/"]')
            )
            if not link:
                continue

            href = link.get("href", "")
            if not href or "/articles/" not in href:
                continue
            if href in seen:
                continue
            seen.add(href)

            if href.startswith("/"):
                href = f"https://www.nature.com{href}"

            urls.append({"url": href})

        logger.info("[Nature:%s] %d article URLs found", code, len(urls))
        return urls

    # ── Detail page fetching (HTTP, metadata from citation_* meta) ──

    def _fetch_detail_pages(self, code, urls, vol, issue):
        """Fetch each article detail page, extract metadata from citation_* meta tags."""
        articles = []
        total = len(urls)
        today = datetime.now().strftime("%Y-%m-%d")

        logger.info("[Nature:%s] Fetching %d detail pages...", code, total)

        for i, entry in enumerate(urls):
            url = entry["url"]
            try:
                html = self._fetch(url, timeout=15)
                if not html or len(html) < 10000:
                    logger.warning("[Nature:%s] Detail page too short: %s", code, url)
                    continue

                soup = BeautifulSoup(html, "html.parser")

                # Collect all citation_* meta tags
                meta = {}
                for m in soup.find_all("meta"):
                    name = m.get("name", "")
                    if name.startswith("citation_"):
                        meta[name] = m.get("content", "")

                # Title: citation_title
                title = meta.get("citation_title", "")
                if not title:
                    # Fallback: h1.c-article-title
                    h1 = soup.select_one("h1.c-article-title")
                    if h1:
                        title = self._clean(h1.get_text())
                if not title or len(title) < 5:
                    continue

                # Authors: citation_author ("Last, First" → "First Last")
                author_metas = [
                    m for m in soup.find_all("meta")
                    if m.get("name") == "citation_author"
                ]
                author_names = []
                for m in author_metas:
                    name = m.get("content", "").strip()
                    if not name:
                        continue
                    # Reverse "Last, First" → "First Last"
                    if ", " in name:
                        parts = name.split(", ", 1)
                        name = f"{parts[1]} {parts[0]}"
                    if not author_names or author_names[-1] != name:
                        author_names.append(name)
                authors = ", ".join(author_names)

                # Date: citation_online_date (YYYY/MM/DD → YYYY-MM-DD)
                pub_date = meta.get("citation_online_date", "").replace("/", "-")[:10]
                if not pub_date:
                    pub_date = today

                # DOI: citation_doi
                doi = meta.get("citation_doi", "")

                # Volume/Issue: only use caller-provided values (from URL structure)
                # citation_volume/issue meta is unreliable for article-number journals
                article_vol = str(vol) if vol else None
                article_iss = str(issue) if issue else None

                # Abstract: #Abs1-content (lsa/ncomms) or .c-article-section__content (nphoton)
                abstract = ""
                abs_el = (
                    soup.select_one("#Abs1-content")
                    or soup.select_one(".c-article-section__content")
                )
                if abs_el:
                    abs_text = self._clean(abs_el.get_text())
                    # Cut at References
                    ref_idx = abs_text.find("References")
                    if ref_idx > 50:
                        abs_text = abs_text[:ref_idx]
                    if len(abs_text) > 50:
                        abstract = abs_text[:5000]

                articles.append({
                    "title": title,
                    "title_cn": "",
                    "authors": authors,
                    "url": url,
                    "doi": doi,
                    "pub_date": pub_date,
                    "journal_ref": (
                        f"{self.journal_name} Vol.{article_vol}"
                        + (f" Issue {article_iss}" if article_iss else "")
                    ),
                    "volume": str(article_vol) if article_vol else None,
                    "issue": str(article_iss) if article_iss else None,
                    "abstract": abstract,
                    "abstract_cn": "",
                })

                if self._on_progress:
                    self._on_progress({"step": f"正在抓取详情", "count": i + 1})

                # Small delay between requests to avoid rate limiting
                if i < total - 1:
                    time.sleep(0.3)

            except Exception:
                logger.exception("[Nature:%s] Detail fetch error: %s", code, url)

        logger.info("[Nature:%s] %d/%d articles fetched from detail pages",
                    code, len(articles), total)
        return articles
