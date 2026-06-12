# scrapers/base.py - Base scraper with common utilities

import re
import time
import logging
import html as html_lib
from datetime import datetime
from typing import List, Dict, Optional, Tuple

import requests

from translator import translate as do_translate

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class BaseScraper:
    """Base class for all journal scrapers."""

    allow_browser: bool = False
    _on_progress = None  # callable(count) for status updates during scrape

    # Override in subclasses
    journal_id: str = ""
    journal_name: str = ""
    journal_name_cn: str = ""
    publisher: str = ""
    journal_type: str = ""
    code: str = ""
    list_url: str = ""
    enabled: bool = True

    def __init__(self):
        self.session = None

    def _clean(self, text: str) -> str:
        if not text:
            return ""
        text = html_lib.unescape(text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"[ -‏ -  ]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _fetch(self, url: str, timeout: int = 30, use_session: bool = False) -> Optional[str]:
        for attempt in range(4):
            try:
                if use_session:
                    if not self.session:
                        self.session = requests.Session()
                        self.session.headers.update(HEADERS)
                    r = self.session.get(url, timeout=timeout)
                else:
                    r = requests.get(url, headers=HEADERS, timeout=timeout)
                if r.status_code == 202:
                    time.sleep(3 + attempt)
                    continue
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                return r.text
            except Exception:
                if attempt < 3:
                    time.sleep(2)
                else:
                    logger.warning("Failed to fetch %s after 4 attempts", url)
                    return None

    def _extract_volume(self, text: str) -> Optional[str]:
        if not text:
            return None
        m = re.search(r"(?:Vol(?:\.|ume)?\s*)?(\d+)\s*\((\d+)\)", text)
        if m:
            return m.group(1)
        m = re.search(r"Volume[:\s]*(\d+)", text, re.I)
        if m:
            return m.group(1)
        m = re.search(r"Vol\.?\s*(\d+)", text, re.I)
        if m:
            return m.group(1)
        return None

    def _extract_issue(self, text: str) -> Optional[str]:
        if not text:
            return None
        # Prefer explicit "Issue/No" patterns over parenthetical numbers
        m = re.search(r"Iss(?:ue)?\.?[:\s]*(\d+)", text, re.I)
        if m:
            return m.group(1)
        m = re.search(r",\s*No\.?\s*(\d+)", text, re.I)
        if m:
            return m.group(1)
        # Fallback: parenthetical number, but skip years (2000-2099)
        m = re.search(r"\((\d+)\)", text)
        if m:
            num = m.group(1)
            year = int(num)
            if not (2000 <= year <= 2099):
                return num
        return None

    def _extract_meta(self, html_text: str, name: str) -> Optional[str]:
        for p in [
            f'<meta[^>]*name="{name}"[^>]*content="([^"]+)"',
            f'<meta[^>]*name="{name.upper()}"[^>]*content="([^"]+)"',
        ]:
            m = re.search(p, html_text, re.I)
            if m:
                return m.group(1)
        return None

    def translate(self, text: str, trans_type: str = "title") -> str:
        """Translate using DeepSeek API. Delegates to shared translator module."""
        return do_translate(text, trans_type)

    def scrape(self) -> Tuple[List[Dict], Optional[str], Optional[str]]:
        """Override in subclass. Returns (articles, volume, issue)."""
        raise NotImplementedError("Subclass must implement scrape()")

    def to_config(self) -> dict:
        return {
            "id": self.journal_id,
            "name": self.journal_name,
            "name_cn": self.journal_name_cn,
            "publisher": self.publisher,
            "type": self.journal_type,
            "code": self.code,
            "list_url": self.list_url,
            "enabled": self.enabled,
        }

    def run_standalone(self):
        """Run scraper independently and print results (for testing).

        Usage: python -m scrapers.opg.aop
        """
        import json as _json

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        print(f"\n{'='*60}")
        print(f"  {self.journal_name} ({self.journal_id})")
        print(f"  {self.list_url}")
        print(f"{'='*60}\n")

        articles, vol, iss = self.scrape()

        print(f"\n{'='*60}")
        print(f"  Results: {len(articles)} articles, Vol {vol}, Issue {iss}")
        print(f"{'='*60}")
        for i, a in enumerate(articles, 1):
            print(f"\n{i:3d}. {a['title'][:100]}")
            if a.get("title_cn"):
                print(f"     CN: {a['title_cn'][:100]}")
            if a.get("authors"):
                print(f"     Authors: {a['authors'][:80]}")
            if a.get("abstract"):
                print(f"     Abstract: {a['abstract'][:120]}...")
        print()
