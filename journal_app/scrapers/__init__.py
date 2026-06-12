# scrapers/__init__.py - Registry of all journal scrapers

import logging

# Browser automation
HAS_BROWSER = False
try:
    from DrissionPage import ChromiumPage, ChromiumOptions  # noqa: F401
    HAS_BROWSER = True
except ImportError:
    pass

from scrapers.opg.aop import scraper as aop
from scrapers.opg.ao import scraper as ao
from scrapers.opg.col import scraper as col
from scrapers.opg.optica import scraper as optica
from scrapers.opg.opticaq import scraper as opticaq
from scrapers.opg.ome import scraper as ome
from scrapers.opg.optcon import scraper as optcon
from scrapers.opg.oe import scraper as oe
from scrapers.opg.ol import scraper as ol
from scrapers.opg.prj import scraper as prj
from scrapers.nature.nphoton import scraper as nphoton
from scrapers.nature.lsa import scraper as lsa
from scrapers.nature.ncomms import scraper as ncomms
from scrapers.wiley.lpr import scraper as lpr
from scrapers.wiley.nanoph import scraper as nanoph
from scrapers.wiley.aom import scraper as aom
from scrapers.wiley.iet_map import scraper as iet_map
from scrapers.springer.elight import scraper as elight
from scrapers.elsevier.ole import scraper as ole
from scrapers.elsevier.olt import scraper as olt
from scrapers.oea import scraper as oea
from scrapers.ieee.tmtt import scraper as tmtt
from scrapers.ieee.mwtl import scraper as mwtl
from scrapers.ieee.tap import scraper as tap
from scrapers.ieee.thz import scraper as thz
from scrapers.ieee.awpl import scraper as awpl
from scrapers.ieee.microwave_mag import scraper as microwave_mag
from scrapers.tandf.jemwa import scraper as jemwa

logger = logging.getLogger(__name__)

# Journal category mapping
JOURNAL_CATEGORIES = {
    # 光学 (Optics/Photonics)
    "aop": "optics", "ao": "optics", "col": "optics", "optica": "optics",
    "opticaq": "optics", "ome": "optics", "optcon": "optics", "oe": "optics",
    "ol": "optics", "prj": "optics",
    "nphoton": "optics", "lsa": "optics", "ncomms": "optics",
    "lpr": "optics", "nanoph": "optics", "aom": "optics",
    "elight": "optics", "ole": "optics", "olt": "optics",
    "oea": "optics",
    # 射频微波 (RF/Microwave/Antennas)
    "tmtt": "rf_microwave", "mwtl": "rf_microwave", "tap": "rf_microwave",
    "thz": "rf_microwave", "awpl": "rf_microwave", "microwave_mag": "rf_microwave",
    "iet_map": "rf_microwave", "jemwa": "rf_microwave",
}

CATEGORY_LABELS = {
    "optics": "🔬 光学",
    "rf_microwave": "📡 射频微波",
}

# All scrapers indexed by journal_id
ALL_SCRAPERS = {
    # OPG (10)
    "aop": aop, "ao": ao, "col": col, "optica": optica, "opticaq": opticaq,
    "ome": ome, "optcon": optcon, "oe": oe, "ol": ol, "prj": prj,
    # Nature (3)
    "nphoton": nphoton, "lsa": lsa, "ncomms": ncomms,
    # Wiley / IET (4)
    "lpr": lpr, "nanoph": nanoph, "aom": aom, "iet_map": iet_map,
    # RSS (3)
    "elight": elight, "ole": ole, "olt": olt,
    # IEEE (6)
    "tmtt": tmtt, "mwtl": mwtl, "tap": tap, "thz": thz,
    "awpl": awpl, "microwave_mag": microwave_mag,
    # T&F (1)
    "jemwa": jemwa,
    # Other (1)
    "oea": oea,
}


def get_scraper(journal_id):
    """Get scraper instance by journal_id."""
    return ALL_SCRAPERS.get(journal_id)


def get_all_scrapers():
    """Get all scrapers as config dicts (for seeding database)."""
    configs = []
    for s in ALL_SCRAPERS.values():
        cfg = s.to_config()
        cfg["category"] = JOURNAL_CATEGORIES.get(s.journal_id, "other")
        configs.append(cfg)
    return configs


def scrape_journal(journal_id, allow_browser=False, browser_address="", skip_urls=None, on_progress=None):
    """Scrape a journal by ID. Returns (articles, volume, issue).

    Args:
        on_progress: Optional callable(count) for incremental status updates.
        browser_address: Optional remote debugging address (e.g. "127.0.0.1:9222")
            to connect to an existing Chrome instead of launching a new one.
        skip_urls: Optional set/frozenset of article URLs that already have
            abstracts — browser mode skips visiting those detail pages.
    """
    scraper = get_scraper(journal_id)
    if not scraper:
        logger.warning("Unknown journal: %s", journal_id)
        return [], None, None
    logger.info("[%s] Scraping %s...", journal_id, scraper.journal_name)

    scraper.allow_browser = allow_browser
    scraper.browser_address = browser_address
    scraper.skip_urls = skip_urls or set()
    scraper._on_progress = on_progress
    articles, vol, iss = scraper.scrape()
    scraper._on_progress = None
    logger.info("[%s] Done: %d articles, V%s I%s", journal_id, len(articles), vol, iss)
    return articles, vol, iss
