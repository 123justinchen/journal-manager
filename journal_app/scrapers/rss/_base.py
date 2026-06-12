# scrapers/rss/_base.py - RSS-based journal scraper

import re
import logging
import html as html_lib
import xml.etree.ElementTree as ET
from datetime import datetime

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Default namespace map for RSS feeds (commonly used by Wiley, Springer, etc.)
NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom": "http://www.w3.org/2005/Atom",
}


class RSSBaseScraper(BaseScraper):
    """RSS-based journals: parse XML feed for articles."""

    journal_type = "wiley"
    rss_url: str = ""

    def scrape(self):
        if not self.rss_url:
            return [], None, None

        logger.info("[RSS:%s] Fetching %s", self.code, self.rss_url)
        xml_text = self._fetch(self.rss_url, timeout=20)
        if not xml_text:
            logger.warning("[RSS:%s] RSS feed unavailable", self.code)
            return [], None, None

        articles = []
        vol, iss = None, None

        skip_words = [
            "Issue Information", "Editorial", "Cover", "Back Cover",
            "Front Cover", "Inside Cover", "Masthead", "Table of Contents",
            "Issue Highlights", "Call for Papers", "Announcement",
        ]

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            logger.warning("[RSS:%s] XML parse error, falling back to regex", self.code)
            return self._parse_regex_fallback(xml_text)

        # Handle both RSS <item> and Atom <entry>
        items = root.findall(".//item")
        if not items:
            items = root.findall(".//atom:entry", NS)

        logger.info("[RSS:%s] Found %d RSS items", self.code, len(items))

        for item in items:
            title = self._rss_text(item, "title")
            if not title or len(title) < 5:
                continue
            if any(s in title for s in skip_words):
                continue

            link = self._rss_text(item, "link")
            # Handle atom:link with href attribute
            if not link:
                link_el = item.find("atom:link", NS)
                if link_el is not None:
                    link = link_el.get("href", "")

            pub_date = self._rss_text(item, "pubDate")
            if not pub_date:
                pub_date = self._rss_text(item, "published")
            if not pub_date:
                pub_date = self._rss_text(item, "dc:date", NS)
            pub_date = pub_date[:10] if pub_date else datetime.now().strftime("%Y-%m-%d")

            # Authors from dc:creator
            creators = [el.text.strip() for el in item.findall("dc:creator", NS) if el.text]
            authors = ", ".join(creators) if creators else ""

            # Description (for volume/issue detection fallback)
            desc = self._rss_text(item, "description")

            # Volume/issue detection
            if not vol and desc:
                vol = self._extract_volume(desc)
                iss = self._extract_issue(desc)
            if not vol and title:
                vol = self._extract_volume(title)

            # Abstract from content:encoded (Wiley RSS) or description fallback
            abstract = ""
            content_raw = self._rss_text(item, "content:encoded", NS)
            if content_raw and len(content_raw) > 50:
                # Strip HTML tags from content:encoded
                clean = html_lib.unescape(content_raw)
                clean = re.sub(r"<[^>]+>", " ", clean)
                clean = re.sub(r"\s+", " ", clean).strip()
                # Remove common non-abstract prefixes
                for prefix in ["Abstract", "Abstract:", "ABSTRACT"]:
                    idx = clean.find(prefix)
                    if 0 <= idx < 100:
                        clean = clean[idx + len(prefix):].strip()
                if len(clean) > 50:
                    abstract = clean[:5000]

            if not abstract and desc and len(desc) > 50:
                clean_desc = re.sub(r"<[^>]+>", "", desc).strip()
                if len(clean_desc) > 50:
                    abstract = clean_desc[:5000]

            title_cn = ""  # translated post-scrape
            abstract_cn = ""  # translated post-scrape

            articles.append({
                "title": title,
                "title_cn": title_cn,
                "authors": authors,
                "url": link,
                "doi": "",
                "pub_date": pub_date,
                "journal_ref": desc[:300] if desc else "",
                "abstract": abstract,
                "abstract_cn": abstract_cn,
                "volume": str(vol) if vol else None,
                "issue": str(iss) if iss else None,
            })
            if self._on_progress:
                self._on_progress(len(articles))

        logger.info("[RSS:%s] %d articles, Vol %s Iss %s", self.code, len(articles), vol, iss)
        return articles, vol, iss

    def _rss_text(self, element, tag, ns=None):
        """Extract text from a child element, with optional namespace.
        Handles both plain text and HTML-wrapped content (e.g. <description><p>...</p></description>).
        """
        el = element.find(tag, ns) if ns else element.find(tag)
        if el is None:
            return ""
        if el.text and el.text.strip():
            return el.text.strip()
        # HTML content wrapped in child tags — get all inner text
        inner = ET.tostring(el, encoding="unicode")
        # Strip outer tag
        inner = re.sub(r"^<[^>]+>", "", inner)
        inner = re.sub(r"</[^>]+>$", "", inner)
        inner = inner.strip()
        if inner:
            inner = html_lib.unescape(inner)
        return inner

    def _parse_regex_fallback(self, xml_text):
        """Fallback RSS parser using regex (for malformed XML)."""
        articles = []
        vol, iss = None, None

        items = re.findall(r"<item>\s*(.*?)\s*</item>", xml_text, re.DOTALL)
        if not items:
            items = re.findall(r"<entry>\s*(.*?)\s*</entry>", xml_text, re.DOTALL)

        logger.info("[RSS:%s] Regex fallback: %d items", self.code, len(items))

        skip_words = [
            "Issue Information", "Editorial", "Cover", "Back Cover",
            "Front Cover", "Inside Cover", "Masthead", "Table of Contents",
            "Issue Highlights", "Call for Papers", "Announcement",
        ]

        for item_xml in items:
            title_m = re.search(r"<title>(?:<!\[CDATA\[)?([^<\]>]*?)(?:\]\]>)?</title>", item_xml, re.I)
            title = self._clean(title_m.group(1)) if title_m else ""
            if not title or len(title) < 5:
                continue
            if any(s in title for s in skip_words):
                continue

            link_m = re.search(r"<link[^>]*>([^<]+)</link>", item_xml)
            link = link_m.group(1) if link_m else ""

            date_m = re.search(r"<(?:dc:date|pubDate|published)>([^<]+)</(?:dc:date|pubDate|published)>", item_xml, re.I)
            pub_date = date_m.group(1)[:10] if date_m else datetime.now().strftime("%Y-%m-%d")

            creator_matches = re.findall(r"<dc:creator>([^<]+)</dc:creator>", item_xml)
            authors = ", ".join(c.strip() for c in creator_matches) if creator_matches else ""

            desc_m = re.search(r"<description>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?\s*</description>", item_xml, re.I)
            desc = self._clean(desc_m.group(1)) if desc_m else ""

            if not vol and desc:
                vol = self._extract_volume(desc)
                iss = self._extract_issue(desc)
            if not vol and title:
                vol = self._extract_volume(title)

            abstract = ""
            content_m = re.search(r"<content:encoded>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?\s*</content:encoded>", item_xml, re.I)
            if content_m:
                raw = content_m.group(1)
                raw_decoded = html_lib.unescape(raw)
                clean = re.sub(r"<[^>]+>", " ", raw_decoded)
                clean = re.sub(r"\s+", " ", clean).strip()
                for prefix in ["Abstract", "Abstract:", "ABSTRACT"]:
                    idx = clean.find(prefix)
                    if 0 <= idx < 100:
                        clean = clean[idx + len(prefix):].strip()
                if len(clean) > 50:
                    abstract = clean[:5000]
            if not abstract and desc and len(desc) > 50:
                clean_desc = re.sub(r"<[^>]+>", "", desc).strip()
                if len(clean_desc) > 50:
                    abstract = clean_desc[:5000]

            title_cn = ""  # translated post-scrape
            abstract_cn = ""  # translated post-scrape

            articles.append({
                "title": title, "title_cn": title_cn,
                "authors": authors, "url": link,
                "doi": "", "pub_date": pub_date,
                "journal_ref": desc[:300] if desc else "",
                "abstract": abstract, "abstract_cn": abstract_cn,
                "volume": str(vol) if vol else None,
                "issue": str(iss) if iss else None,
            })

        logger.info("[RSS:%s] Regex fallback: %d articles", self.code, len(articles))
        return articles, vol, iss
