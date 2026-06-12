# scrapers/oea.py - Opto-Electronic Advances

import re
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class OEAScraper(BaseScraper):
    journal_id = "oea"
    journal_name = "Opto-Electronic Advances"
    journal_name_cn = "光电进展"
    publisher = "OEA"
    journal_type = "oea"
    code = "oea"
    list_url = "https://www.oejournal.org/oea/article/current"

    def scrape(self):
        logger.info("[OEA] Fetching %s", self.list_url)
        html = self._fetch(self.list_url, timeout=20)
        if not html:
            return [], None, None

        soup = BeautifulSoup(html, "html.parser")
        today = datetime.now().strftime("%Y-%m-%d")

        articles = []
        seen_dois = set()

        # Structure: div.article-list.preload-article-list
        #   div.article-list-left
        #   div.article-list-right
        #     div.article-list-title > a  → title + DOI URL
        #     div.article-list-author      → authors
        #     div.article-list-time        → "2026, 9(6): 250255. DOI: ..."

        for item in soup.select("div.article-list.preload-article-list"):
            try:
                # Title + DOI
                title_a = item.select_one("div.article-list-title a")
                if not title_a:
                    continue
                title = self._clean(title_a.get_text())
                if len(title) < 10:
                    continue

                href = title_a.get("href", "")
                doi_match = re.search(r"(10\.29026/oea\.\d{4}\.\d+)", href)
                doi = doi_match.group(1) if doi_match else ""
                if doi in seen_dois:
                    continue
                seen_dois.add(doi)

                article_url = f"https://www.oejournal.org{href}" if href.startswith("/") else href

                # Authors
                authors = ""
                author_div = item.select_one("div.article-list-author")
                if author_div:
                    authors = self._clean(author_div.get_text())

                # Citation: "2026, 9(6): 250255. DOI: ..."
                pub_date = today
                volume = None
                issue = None
                time_div = item.select_one("div.article-list-time")
                if time_div:
                    time_text = self._clean(time_div.get_text())
                    cit_match = re.search(
                        r"(\d{4}),\s*(\d+)\s*\(\s*(\d+)\s*\)",
                        time_text,
                    )
                    if cit_match:
                        pub_date = f"{cit_match.group(1)}-01-01"
                        volume = cit_match.group(2)
                        issue = cit_match.group(3)

                articles.append({
                    "title": title,
                    "title_cn": "",
                    "authors": authors,
                    "url": article_url,
                    "doi": doi,
                    "pub_date": pub_date,
                    "journal_ref": "",
                    "abstract": "",
                    "abstract_cn": "",
                    "volume": volume,
                    "issue": issue,
                })
                if self._on_progress:
                    self._on_progress(len(articles))

            except Exception:
                logger.exception("[OEA] Parse error for article item")

        # Fetch abstracts from article detail pages
        self._fetch_abstracts(articles)

        logger.info("[OEA] %d articles", len(articles))
        return articles, None, None

    def _fetch_abstracts(self, articles):
        """Fetch abstracts and precise dates from article detail pages."""
        missing = [a for a in articles if not a.get("abstract") or len(a.get("abstract", "")) < 50]
        if not missing:
            return
        logger.info("[OEA] Fetching %d abstracts from detail pages...", len(missing))
        for art in articles:
            try:
                url = art["url"]
                html = self._fetch(url, timeout=10)
                if not html:
                    continue
                soup = BeautifulSoup(html, "html.parser")

                # Extract precise publication date from meta
                for meta_name in ("dc.date", "citation_date", "citation_online_date"):
                    meta = soup.find("meta", attrs={"name": meta_name})
                    if meta and meta.get("content"):
                        date_val = meta["content"].strip()[:10]
                        if len(date_val) == 10 and date_val[4] == "-":
                            art["pub_date"] = date_val
                            break

                # Skip abstract if already decent
                if art.get("abstract") and len(art.get("abstract", "")) >= 50:
                    continue

                # Try meta tags for abstract
                for meta_name in ("dc.description", "twitter:description", "citation_abstract"):
                    meta = soup.find("meta", attrs={"name": meta_name})
                    if meta and meta.get("content"):
                        raw = meta["content"]
                        clean = re.sub(r"<[^>]+>", " ", raw)
                        clean = re.sub(r"\s+", " ", clean).strip()
                        if len(clean) > 50:
                            art["abstract"] = clean[:5000]
                            art["abstract_cn"] = ""
                            break
                # Fallback: look for abstract heading + sibling
                if not art.get("abstract"):
                    abs_heading = soup.find(
                        lambda tag: tag.name in ("h2", "h3", "h4", "div")
                        and "abstract" in (tag.get_text(strip=True).lower() or "")
                        and len(tag.get_text(strip=True)) < 30
                    )
                    if abs_heading:
                        abs_el = abs_heading.find_next_sibling("div")
                        if abs_el:
                            clean = self._clean(abs_el.get_text())
                            if len(clean) > 50:
                                art["abstract"] = clean[:5000]
                                art["abstract_cn"] = ""
            except Exception:
                logger.exception("[OEA] Detail page error for %s", art.get("url", "?"))


scraper = OEAScraper()

if __name__ == "__main__":
    scraper.run_standalone()
