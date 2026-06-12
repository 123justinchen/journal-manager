# scrapers/tandf/_base.py - Taylor & Francis journal scraper (browser mode)

import re
import time
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class TandFBaseScraper(BaseScraper):
    """Taylor & Francis journals: tandfonline.com.

    T&F returns 403 for HTTP scraping, so browser mode is used.
    """

    journal_type = "tandf"
    publisher = "Taylor & Francis"

    def scrape(self):
        code = self.code
        url = self.list_url
        if not url:
            return [], None, None
        if not self.allow_browser:
            logger.warning("[T&F:%s] Browser required but not available", code)
            return [], None, None

        logger.info("[T&F:%s] Fetching %s", code, url)

        from DrissionPage import ChromiumPage, ChromiumOptions

        co = ChromiumOptions()
        co.set_argument("--no-sandbox")
        co.set_argument("--disable-blink-features=AutomationControlled")
        co.set_argument("--lang=en-US")
        co.set_load_mode("eager")
        co.set_timeouts(page_load=30)

        browser_addr = getattr(self, "browser_address", "")
        if browser_addr:
            co.set_address(browser_addr)
            logger.info("[T&F:%s] Connecting to existing browser at %s", code, browser_addr)

        page = ChromiumPage(co)
        articles = []
        today = datetime.now().strftime("%Y-%m-%d")
        seen_dois = set()

        try:
            page.get(url)
            self._wait_for_page(page, min_len=50000)

            html = page.html
            if len(html) < 5000:
                logger.error("[T&F:%s] Page too short (%d bytes) — likely blocked", code, len(html))
                return [], None, None

            soup = BeautifulSoup(html, "html.parser")

            # Extract volume/issue
            vol, iss = self._extract_vol_iss(soup)

            # Find article entries — prefer .tocArticle (current issue only)
            # .articleEntry also matches "Explore articles" recommendations — avoid
            entries = soup.select(".tocArticle, [class*=toc-article]")
            if not entries:
                entries = soup.select(
                    "div.artDetails, [class*=article-entry], .article-meta"
                )
            if not entries:
                # Fallback: find article title links
                entries = []
                for a in soup.find_all("a", href=re.compile(r"/doi/(?:full|abs)/10\.\d+")):
                    p = a.parent
                    for _ in range(5):
                        if p and p.name in ("div", "article"):
                            if p not in entries:
                                entries.append(p)
                            break
                        p = p.parent if p else None

            logger.info("[T&F:%s] Found %d article entries", code, len(entries))

            for entry in entries:
                try:
                    # Title
                    title_el = entry.select_one(
                        "a[href*='/doi/'], .articleTitle a, h2 a, h3 a, [class*=title] a"
                    )
                    if not title_el:
                        title_el = entry.find("a", href=re.compile(r"/doi/(?:full|abs)/"))
                    if not title_el:
                        continue
                    title = self._clean(title_el.get_text())
                    if len(title) < 10:
                        continue

                    href = title_el.get("href", "")
                    doi_match = re.search(r"10\.\d{4,}/[^\s\"&?]+", href)
                    if not doi_match:
                        doi_match = re.search(r"10\.\d{4,}/[^\s\"&?]+", entry.get_text(" ", strip=True))
                    doi = doi_match.group(0).rstrip(".") if doi_match else ""
                    if doi in seen_dois:
                        continue
                    seen_dois.add(doi)

                    # Full URL
                    if href.startswith("/"):
                        article_url = f"https://www.tandfonline.com{href}"
                    else:
                        article_url = href if href.startswith("http") else f"https://www.tandfonline.com/doi/abs/{doi}"

                    # Authors
                    authors = ""
                    author_el = entry.select_one(
                        "[class*=authors], [class*=Authors], .contributors, "
                        "[class*=author-list], span.authors"
                    )
                    if author_el:
                        authors = self._clean(author_el.get_text())

                    # Date
                    pub_date = today
                    date_el = entry.select_one("[class*=date], [class*=pub], .published, time")
                    if date_el:
                        date_text = self._clean(date_el.get_text())
                        pub_date = self._parse_date(date_text) or today

                    # Volume/issue from entry
                    entry_text = entry.get_text(" ", strip=True)
                    e_vol = vol
                    e_iss = iss
                    if not e_vol:
                        e_vol = self._extract_volume(entry_text)
                    if not e_iss:
                        e_iss = self._extract_issue(entry_text)

                    articles.append({
                        "title": title,
                        "title_cn": "",
                        "authors": authors,
                        "url": article_url,
                        "doi": doi,
                        "pub_date": pub_date,
                        "journal_ref": f"Vol.{e_vol}" + (f" Iss.{e_iss}" if e_iss else "") if e_vol else "",
                        "abstract": "",
                        "abstract_cn": "",
                        "volume": str(e_vol) if e_vol else None,
                        "issue": str(e_iss) if e_iss else None,
                    })
                    if self._on_progress:
                        self._on_progress(len(articles))

                except Exception:
                    logger.exception("[T&F:%s] Parse error for article entry", code)

            # Fetch abstracts
            if articles:
                self._fetch_abstracts(page, articles)

        finally:
            try:
                if not browser_addr:
                    page.quit()
            except Exception:
                pass

        logger.info("[T&F:%s] %d articles, Vol %s Iss %s", code, len(articles), vol, iss)
        return articles, vol, iss

    # ── Helpers ─────────────────────────────────────────────────────

    def _wait_for_page(self, page, min_len=30000, timeout=30):
        for _ in range(timeout):
            time.sleep(1)
            try:
                if len(page.html) > min_len:
                    return
            except Exception:
                pass
        logger.warning("[T&F:%s] Page load timeout", self.code)

    def _extract_vol_iss(self, soup):
        vol, iss = None, None
        title = soup.find("title")
        page_text = title.get_text() if title else ""
        vol = self._extract_volume(page_text)
        iss = self._extract_issue(page_text)
        if not vol or not iss:
            for h in soup.find_all(["h1", "h2", "h3"]):
                h_text = self._clean(h.get_text())
                if not vol:
                    vol = self._extract_volume(h_text)
                if not iss:
                    iss = self._extract_issue(h_text)
                if vol and iss:
                    break
        # Filter out years masquerading as issue numbers (e.g. "2026")
        if iss and len(iss) == 4 and iss.isdigit():
            year = int(iss)
            if 2000 <= year <= 2099:
                iss = None
        return vol, iss

    def _parse_date(self, text):
        import re as _re
        for fmt, pat in [
            ("%d %B %Y", r"(\d{1,2}\s+\w+\s+\d{4})"),
            ("%d %b %Y", r"(\d{1,2}\s+\w{3}\s+\d{4})"),
            ("%B %d, %Y", r"(\w+\s+\d{1,2},\s*\d{4})"),
            ("%Y-%m-%d", r"(\d{4}-\d{2}-\d{2})"),
            ("%d/%m/%Y", r"(\d{1,2}/\d{1,2}/\d{4})"),
        ]:
            m = _re.search(pat, text)
            if m:
                try:
                    return datetime.strptime(m.group(1), fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
        return ""

    def _fetch_abstracts(self, page, articles):
        """Visit detail pages for abstracts."""
        missing = [a for a in articles if not a.get("abstract") or len(a.get("abstract", "")) < 50]
        if not missing:
            return
        logger.info("[T&F:%s] Fetching %d abstracts...", self.code, len(missing))

        for art in missing:
            try:
                # Try abs URL first (often works without full page load)
                doi = art["doi"]
                if doi:
                    abs_url = f"https://www.tandfonline.com/doi/abs/{doi}"
                else:
                    abs_url = art["url"]

                page.get(abs_url)
                self._wait_for_page(page, min_len=10000, timeout=20)
                soup = BeautifulSoup(page.html, "html.parser")

                # Try meta tags
                abstract = ""
                for meta_name in ("dc.description", "citation_abstract", "description"):
                    meta = soup.find("meta", attrs={"name": meta_name})
                    if meta and meta.get("content"):
                        clean = re.sub(r"<[^>]+>", " ", meta["content"])
                        clean = re.sub(r"\s+", " ", clean).strip()
                        if len(clean) > 50:
                            abstract = clean[:5000]
                            break

                # Fallback: abstract div (try specific selectors first)
                if not abstract:
                    for sel in (".hlFld-Abstract", "[id*=abstract]", "[class*=abstract]"):
                        for el in soup.select(sel):
                            # Skip keyword-only blocks
                            classes = " ".join(el.get("class", []))
                            if "keyword" in classes.lower():
                                continue
                            clean = self._clean(el.get_text())
                            clean = re.sub(r"^(?:Abstract|ABSTRACT)\s*:?\s*", "", clean, flags=re.I)
                            if len(clean) > 50:
                                abstract = clean[:5000]
                                break
                        if abstract:
                            break

                if abstract:
                    art["abstract"] = abstract
                    art["abstract_cn"] = ""

                # Precise date
                for meta_name in ("dc.date", "citation_date", "citation_online_date"):
                    meta = soup.find("meta", attrs={"name": meta_name})
                    if meta and meta.get("content"):
                        d = meta["content"].strip()[:10]
                        if len(d) == 10 and d[4] == "-":
                            art["pub_date"] = d
                            break

            except Exception:
                logger.exception("[T&F:%s] Detail fetch error for %s", self.code, art.get("url", "?"))
