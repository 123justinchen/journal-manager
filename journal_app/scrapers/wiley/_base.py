# scrapers/wiley/_base.py - Wiley journal TOC scraper (browser-based, Cloudflare bypass)

import re
import time
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class WileyTOCScraper(BaseScraper):
    """Wiley journals: TOC page → discover article URLs → detail pages → full metadata.

    Wiley pages are Cloudflare-protected — always use browser (DrissionPage).
    TOC page provides only article URLs/DOIs. All metadata (title, authors,
    abstract, pub_date) comes from article detail pages via meta tags.
    """

    journal_type = "wiley"
    publisher = "Wiley"
    toc_id: str = ""
    toc_domain: str = "advanced.onlinelibrary.wiley.com"

    # ── Main entry ───────────────────────────────────────────────────

    def scrape(self):
        if not self.toc_id:
            logger.warning("[Wiley:%s] No toc_id configured", self.code)
            return [], None, None

        toc_url = f"https://{self.toc_domain}/toc/{self.toc_id}/current"
        return self._scrape_with_browser(toc_url)

    # ── Browser mode ─────────────────────────────────────────────────

    def _scrape_with_browser(self, toc_url):
        """1. Load TOC → extract article URLs + Vol/Issue
           2. Visit each article detail page → extract full metadata."""
        logger.info("[Wiley:%s] Browser: loading %s", self.code, toc_url)

        from DrissionPage import ChromiumPage, ChromiumOptions

        co = ChromiumOptions()
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-blink-features=AutomationControlled')

        page = ChromiumPage(co)
        try:
            # Step 1: Load TOC page 1, extract URLs + vol/issue + page links
            page.get(toc_url)
            for _ in range(15):
                time.sleep(1)
                html = page.html
                if len(html) > 50000 and 'challenges.cloudflare.com' not in html:
                    break
                if self._on_progress:
                    self._on_progress(0)

            if len(page.html) < 10000 or 'challenges.cloudflare.com' in page.html:
                logger.warning("[Wiley:%s] TOC page failed to load", self.code)
                return [], None, None

            all_urls, vol, iss, page_links = self._extract_toc_urls(page.html)

            # Step 1b: Fetch additional pages if pagination exists
            for page_url in page_links:
                page.get(page_url)
                for _ in range(15):
                    time.sleep(0.5)
                    if len(page.html) > 50000:
                        break
                more_urls, _, _, _ = self._extract_toc_urls(page.html)
                # Merge unique
                seen = {u["url"] for u in all_urls}
                for u in more_urls:
                    if u["url"] not in seen:
                        all_urls.append(u)
                        seen.add(u["url"])
                if self._on_progress:
                    self._on_progress(0)

            logger.info("[Wiley:%s] %d articles across all pages", self.code, len(all_urls))

            # Step 2: Visit each article detail page for full metadata
            articles = self._fetch_article_details(page, all_urls, vol, iss)

            return articles, vol, iss

        finally:
            try:
                page.quit()
            except Exception:
                pass

    def _extract_toc_urls(self, html):
        """Extract article URLs/DOIs, volume/issue, and pagination links from TOC page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        seen_dois = set()
        page_links = []
        seen_pages = set()

        # Volume/issue from page title
        vol, iss = None, None
        title_tag = soup.find("title")
        if title_tag:
            vm = re.search(r"Vol\s*(\d+).*?(?:No|Issue)\s*(\d+)", title_tag.get_text(strip=True), re.I)
            if vm:
                vol, iss = vm.group(1), vm.group(2)

        # Extract pagination links (non-active pages only)
        pagination = soup.select_one('.pagination__list')
        if pagination:
            for a in pagination.find_all('a', href=True):
                href = a.get("href", "")
                cls = a.get("class", [])
                if isinstance(cls, str):
                    cls = [cls]
                if "active" in cls:
                    continue
                page_num = a.get("title", "").strip()
                if page_num and page_num.isdigit() and page_num not in seen_pages:
                    seen_pages.add(page_num)
                    if href.startswith("/"):
                        full = f"https://{self.toc_domain}{href}"
                    elif href.startswith("http"):
                        full = href
                    else:
                        full = f"https://{self.toc_domain}/{href}"
                    page_links.append(full)

        # Extract unique article URLs from issue-item elements
        for item in soup.select('[class*=issue-item]'):
            for a in item.select('a[href*="/doi/"]'):
                href = a.get("href", "")
                if "/doi/10." not in href and "/doi/abs/" not in href:
                    continue
                doi_match = re.search(r"10\.\d{4,}/[a-zA-Z0-9.\-]+", href)
                if not doi_match:
                    continue
                doi = doi_match.group(0)
                if doi in seen_dois:
                    continue
                seen_dois.add(doi)

                title_text = self._clean(a.get_text())
                if not title_text or len(title_text) < 10:
                    continue
                if "Issue Information" in title_text:
                    continue

                if href.startswith("/"):
                    full_url = f"https://{self.toc_domain}{href}"
                elif href.startswith("http"):
                    full_url = href
                else:
                    full_url = f"https://{self.toc_domain}/{href}"

                urls.append({"url": full_url, "doi": doi})
                break  # only first valid DOI link per item

        if page_links:
            logger.info("[Wiley:%s] Page 1: %d URLs, %d more pages, Vol %s Iss %s",
                        self.code, len(urls), len(page_links), vol, iss)
        else:
            logger.info("[Wiley:%s] TOC: %d unique article URLs, Vol %s Iss %s",
                        self.code, len(urls), vol, iss)
        return urls, vol, iss, page_links

    def _fetch_article_details(self, page, urls, vol, iss):
        """Visit each article detail page, extract full metadata from meta tags."""
        articles = []
        total = len(urls)
        today = datetime.now().strftime("%Y-%m-%d")

        for i, entry in enumerate(urls):
            url = entry["url"]
            doi = entry["doi"]
            try:
                page.get(url)
                # Wait for page load
                for _ in range(20):
                    time.sleep(0.5)
                    html = page.html
                    if len(html) > 50000:
                        break

                soup = BeautifulSoup(page.html, "html.parser")

                # Collect all citation_* meta tags
                meta = {}
                for m in soup.find_all("meta"):
                    name = m.get("name", "")
                    if name.startswith("citation_"):
                        meta[name] = m.get("content", "")

                # Title: from meta or page
                title = meta.get("citation_title", "")
                if not title:
                    title_tag = soup.find("title")
                    if title_tag:
                        # Strip " - Author - Journal - Wiley Online Library" suffix
                        t = title_tag.get_text(strip=True)
                        if " - " in t:
                            # Remove everything after the first " - " that's likely a separator
                            parts = t.split(" - ")
                            if len(parts) > 2:
                                t = " - ".join(parts[:-2])
                            else:
                                t = parts[0]
                        title = self._clean(t)
                if not title or len(title) < 10:
                    title = entry.get("title_override", "") or title

                # Authors: from citation_author meta tags (multiple)
                author_metas = [m for m in soup.find_all("meta") if m.get("name") == "citation_author"]
                authors = ", ".join(m.get("content", "") for m in author_metas if m.get("content"))

                # Pub date: citation_online_date (First Published)
                pub_date = meta.get("citation_online_date", "").replace("/", "-")[:10]
                if not pub_date:
                    epub_el = soup.select_one('[class*="epub-date"]')
                    if epub_el:
                        try:
                            parsed = datetime.strptime(epub_el.get_text(strip=True), "%d %B %Y")
                            pub_date = parsed.strftime("%Y-%m-%d")
                        except ValueError:
                            pass
                if not pub_date:
                    pub_date = today

                # Abstract: from article body
                abstract = ""
                abs_section = (
                    soup.select_one('[class*="article-section__abstract"]')
                    or soup.select_one('[class*="abstract-group"]')
                    or soup.select_one('section[class*="abstract"]')
                    or soup.select_one('.article-body')
                )
                if abs_section:
                    abs_text = self._clean(abs_section.get_text())
                    # Strip leading "Abstract" / "ABSTRACT" prefix
                    for prefix in ["Abstract", "ABSTRACT", "Abstract:"]:
                        if abs_text.startswith(prefix):
                            abs_text = abs_text[len(prefix):].strip()
                            break
                    ref_idx = abs_text.find("References")
                    if ref_idx > 50:
                        abs_text = abs_text[:ref_idx]
                    if len(abs_text) > 50:
                        abstract = abs_text[:5000]

                # Update volume/issue from meta (more reliable than TOC title)
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
                logger.exception("[Wiley:%s] Detail fetch error: %s", self.code, url)
                # Insert a minimal entry so we don't lose the article entirely
                articles.append({
                    "title": "",
                    "title_cn": "",
                    "authors": "",
                    "url": url,
                    "doi": doi,
                    "pub_date": today,
                    "journal_ref": "",
                    "volume": str(vol) if vol else None,
                    "issue": str(iss) if iss else None,
                    "abstract": "",
                    "abstract_cn": "",
                })

        logger.info("[Wiley:%s] %d articles extracted from detail pages", self.code, len(articles))
        return articles

