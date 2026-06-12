# scrapers/rss/elight.py - eLight (Springer Open)

import re
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class ElightScraper(BaseScraper):
    journal_id = "elight"
    journal_name = "eLight"
    journal_name_cn = "eLight"
    publisher = "Springer Nature"
    journal_type = "springer"
    code = "elight"
    list_url = "https://link.springer.com/journal/43593/volumes-and-issues"
    _journal_home = "https://link.springer.com/journal/43593"

    def scrape(self):
        logger.info("[eLight] Fetching volumes-and-issues: %s", self.list_url)
        html = self._fetch(self.list_url, timeout=20)
        if not html:
            return [], None, None

        soup = BeautifulSoup(html, "html.parser")
        today = datetime.now().strftime("%Y-%m-%d")

        # Step 1: Find the latest issue link
        # Patterns: /journal/43593/volumes-and-issues/6-1 or /journal/43593/volume-6/issue-1
        latest_href = ""
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            m = re.search(r"/journal/43593/volumes-and-issues/(\d+-\d+)", href)
            if m:
                latest_href = href
                break  # First one is the latest
        if not latest_href:
            # Try alternative pattern
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                m = re.search(r"/journal/43593/volumes-and-issues/\d+-\d+", href)
                if m:
                    latest_href = href
                    break

        if latest_href:
            issue_url = f"https://link.springer.com{latest_href}"
        else:
            logger.warning("[eLight] No issue link found on volumes-and-issues page")
            return [], None, None

        # Step 2: Extract volume/issue from URL
        m = re.search(r"volumes-and-issues/(\d+)-(\d+)", latest_href)
        vol = m.group(1) if m else None
        iss = m.group(2) if m else None
        logger.info("[eLight] Latest issue: Vol %s, Iss %s → %s", vol, iss, issue_url)

        # Step 3: Fetch the issue page
        issue_html = self._fetch(issue_url, timeout=20)
        if not issue_html:
            return [], None, None

        issue_soup = BeautifulSoup(issue_html, "html.parser")
        articles = []
        seen_dois = set()

        # Use <article> tags for precise article cards
        cards = issue_soup.select("article")
        if not cards:
            # Fallback: broader selector with dedup
            cards = issue_soup.select("[class*=app-card-open]")

        logger.info("[eLight] Found %d article cards", len(cards))

        for card in cards:
            try:
                # Title
                title_a = card.select_one("h2.app-card-open__heading a, h3.app-card-open__heading a")
                if not title_a:
                    title_a = card.select_one("a[href*='/article/']")
                if not title_a:
                    continue
                title = self._clean(title_a.get_text())
                if len(title) < 10:
                    continue

                href = title_a.get("href", "")
                doi_match = re.search(r"10\.\d{4,}/[^/]+\d", href)
                doi = doi_match.group(0) if doi_match else ""
                if doi in seen_dois:
                    continue
                seen_dois.add(doi)

                article_url = f"https://link.springer.com{href}" if href.startswith("/") else href

                # Authors from <li> items inside author list
                authors = ""
                author_items = card.select("ul.app-author-list li, [class*=author-list] li, span[itemprop='author']")
                if author_items:
                    author_names = [self._clean(li.get_text()) for li in author_items]
                    author_names = [n for n in author_names if n and len(n) > 1]
                    authors = ", ".join(author_names)
                if not authors:
                    author_div = card.select_one("div.app-card-open__authors, [class*=authors]")
                    if author_div:
                        authors = self._clean(author_div.get_text())

                # Date from meta items
                pub_date = today
                for meta_span in card.select("span.c-meta__item, [class*=meta__item]"):
                    txt = self._clean(meta_span.get_text())
                    dm = re.match(r"(\d{1,2}\s+\w+\s+\d{4})", txt)
                    if dm:
                        try:
                            pub_date = datetime.strptime(dm.group(1), "%d %B %Y").strftime("%Y-%m-%d")
                        except ValueError:
                            pub_date = today
                        break

                articles.append({
                    "title": title,
                    "title_cn": "",
                    "authors": authors,
                    "url": article_url,
                    "doi": doi,
                    "pub_date": pub_date,
                    "journal_ref": f"Vol.{vol}" + (f" Iss.{iss}" if iss else "") if vol else "",
                    "abstract": "",
                    "abstract_cn": "",
                    "volume": str(vol) if vol else None,
                    "issue": str(iss) if iss else None,
                })
                if self._on_progress:
                    self._on_progress(len(articles))

            except Exception:
                logger.exception("[eLight] Parse error for article card")

        # Step 4: Fetch abstracts from article detail pages
        self._fetch_abstracts(articles)

        logger.info("[eLight] %d articles, Vol %s Iss %s", len(articles), vol, iss)
        return articles, vol, iss

    def _fetch_abstracts(self, articles):
        """Fetch abstracts from article detail pages."""
        missing = [a for a in articles if not a.get("abstract") or len(a.get("abstract", "")) < 50]
        if not missing:
            return
        logger.info("[eLight] Fetching %d abstracts from detail pages...", len(missing))
        for art in missing:
            try:
                html = self._fetch(art["url"], timeout=15)
                if not html:
                    continue
                soup = BeautifulSoup(html, "html.parser")
                # Springer article page: abstract in section with id or data-title
                for sel in ("[data-title='Abstract']", "[id*='Abs']", "[class*='Abstract']",
                            "#Abs1-content", "[class*='c-article-section']"):
                    el = soup.select_one(sel)
                    if el:
                        clean = self._clean(el.get_text())
                        # Remove leading "Abstract" label
                        clean = re.sub(r"^Abstract\s*", "", clean, flags=re.I)
                        if len(clean) > 50:
                            art["abstract"] = clean[:5000]
                            art["abstract_cn"] = ""
                            break
                # Fallback: try meta
                if not art.get("abstract"):
                    for meta_name in ("dc.description", "citation_abstract", "description"):
                        meta = soup.find("meta", attrs={"name": meta_name})
                        if meta and meta.get("content"):
                            clean = re.sub(r"<[^>]+>", " ", meta["content"])
                            clean = re.sub(r"\s+", " ", clean).strip()
                            if len(clean) > 50:
                                art["abstract"] = clean[:5000]
                                art["abstract_cn"] = ""
                                break
            except Exception:
                logger.exception("[eLight] Abstract fetch error for %s", art.get("url", "?"))


scraper = ElightScraper()

if __name__ == "__main__":
    scraper.run_standalone()
