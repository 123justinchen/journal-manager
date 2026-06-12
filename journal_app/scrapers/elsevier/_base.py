# scrapers/elsevier/_base.py - Elsevier ScienceDirect browser scraper

import re
import time
import random
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class ElsevierBaseScraper(BaseScraper):
    """Elsevier ScienceDirect: issues → latest volume → detail pages.

    Detail pages may trigger robot check — user solves manually.
    ScienceDirect rate-limits aggressively; long random delays
    between detail page requests help avoid IP blocks.
    """

    journal_type = "elsevier"
    publisher = "Elsevier"
    journal_url: str = ""
    _detail_delay_min = 8   # seconds between detail page requests
    _detail_delay_max = 15

    def scrape(self):
        if not self.journal_url:
            return [], None, None

        from DrissionPage import ChromiumPage, ChromiumOptions

        co = ChromiumOptions()
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_load_mode('eager')
        co.set_timeouts(page_load=15)

        page = ChromiumPage(co)
        articles = []

        try:
            # Step 1: Load issues page, find latest volume
            issues_url = f"{self.journal_url}/issues"
            logger.info("[Elsevier:%s] Loading issues: %s", self.code, issues_url)
            page.get(issues_url)
            for _ in range(20):
                time.sleep(1)
                if len(page.html) > 50000:
                    break

            soup = BeautifulSoup(page.html, "html.parser")
            latest_link = soup.select_one('a[href*="/vol/"]')
            if not latest_link:
                logger.warning("[Elsevier:%s] No volume links found", self.code)
                return [], None, None

            vol_href = latest_link.get("href", "")
            if vol_href.startswith("/"):
                vol_href = f"https://www.sciencedirect.com{vol_href}"
            vol_match = re.search(r"/vol/(\d+)", vol_href)
            vol = vol_match.group(1) if vol_match else None
            logger.info("[Elsevier:%s] Latest: Vol.%s", self.code, vol)
            if self._on_progress:
                self._on_progress({
                    "step": f"找到最新卷 Vol.{vol}，提取文章链接...",
                    "count": 0,
                })

            # Step 2: Load volume page, extract article URLs
            page.get(vol_href)
            for _ in range(20):
                time.sleep(1)
                if len(page.html) > 50000:
                    break

            soup = BeautifulSoup(page.html, "html.parser")
            urls = []
            seen = set()
            for a in soup.select('a[href*="/science/article/pii/"]'):
                href = a.get("href", "")
                if "/pdfft" in href:
                    continue
                if href in seen:
                    continue
                seen.add(href)
                if href.startswith("/"):
                    href = f"https://www.sciencedirect.com{href}"
                urls.append({"url": href, "listing_title": a.get_text(strip=True)})

            logger.info("[Elsevier:%s] %d article URLs found", self.code, len(urls))

            # Filter out already-saved URLs so re-scrape gets new ones
            try:
                from database import db_connection
                with db_connection() as conn:
                    existing = set(
                        r[0] for r in conn.execute(
                            "SELECT url FROM articles WHERE journal_id=?", (self.journal_id,)
                        ).fetchall()
                    )
                urls = [u for u in urls if u["url"] not in existing]
                logger.info("[Elsevier:%s] %d new, %d already in DB",
                            self.code, len(urls), len(existing))
            except Exception:
                logger.exception("[Elsevier:%s] Failed to check existing URLs", self.code)
            # Limit per scrape to avoid rate limiting
            urls = urls[:8]

            # Step 3: Fetch detail pages
            articles = self._fetch_detail_pages(page, urls, vol)

        finally:
            try:
                page.quit()
            except Exception:
                pass

        return articles, vol, None

    def _fetch_detail_pages(self, page, urls, vol):
        """Visit each article detail page, extract metadata."""
        articles = []
        total = len(urls)
        today = datetime.now().strftime("%Y-%m-%d")
        ROBOT_MARKER = "Are you a robot"

        for i, entry in enumerate(urls):
            url = entry["url"]
            try:
                page.get(url)
                # Wait for page, detect robot check
                for _ in range(20):
                    time.sleep(1)
                    html_text = page.html
                    if ROBOT_MARKER in html_text:
                        logger.warning(
                            "[Elsevier:%s] [!] Robot check on %s — solve in browser",
                            self.code, url,
                        )
                        for attempt in range(300):
                            time.sleep(1)
                            html_text = page.html
                            if ROBOT_MARKER not in html_text and len(html_text) > 50000:
                                logger.info(
                                    "[Elsevier:%s] Robot solved after ~%ds",
                                    self.code, attempt,
                                )
                                break
                        else:
                            raise TimeoutError("Robot check timeout")
                        break
                    if len(html_text) > 100000:
                        break

                soup = BeautifulSoup(page.html, "html.parser")

                # Collect meta tags
                meta = {}
                for m in soup.find_all("meta"):
                    name = m.get("name", "")
                    if name.startswith("citation_"):
                        meta[name] = m.get("content", "")

                # Title
                title = meta.get("citation_title", "")
                if not title:
                    title_el = soup.select_one("h1.title-text")
                    if title_el:
                        title = self._clean(title_el.get_text())
                if not title or len(title) < 5:
                    title = entry.get("listing_title", "")

                # Authors: citation_author meta
                author_metas = [
                    m for m in soup.find_all("meta")
                    if m.get("name") == "citation_author"
                ]
                author_names = []
                for m in author_metas:
                    name = m.get("content", "").strip()
                    if name and (not author_names or author_names[-1] != name):
                        author_names.append(name)
                authors = ", ".join(author_names)

                # Date
                pub_date = (
                    meta.get("citation_online_date", "")
                    or meta.get("citation_publication_date", "")
                ).replace("/", "-")[:10]
                if not pub_date:
                    pub_date = today

                # DOI
                doi = meta.get("citation_doi", "")
                if not doi:
                    doi_m = re.search(r"10\.\d{4,}/[a-zA-Z0-9.\-]+", page.html)
                    if doi_m:
                        doi = doi_m.group(0)

                # Volume/Issue
                article_vol = meta.get("citation_volume", "") or str(vol) if vol else None
                article_iss = meta.get("citation_issue", "") or None

                # Abstract
                abstract = ""
                abs_el = (
                    soup.select_one("#abstract")
                    or soup.select_one('[class*="abstract"]')
                    or soup.select_one(".article-abstract")
                )
                if abs_el:
                    abs_text = self._clean(abs_el.get_text())
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
                    self._on_progress({
                        "step": f"正在抓取详情",
                        "count": i + 1,
                    })

            except Exception:
                logger.exception("[Elsevier:%s] Detail fetch error: %s", self.code, url)

            # Random delay between requests
            if i < total - 1:
                delay = random.randint(self._detail_delay_min, self._detail_delay_max)
                time.sleep(delay)

        logger.info("[Elsevier:%s] %d/%d articles fetched", self.code, len(articles), total)
        return articles
