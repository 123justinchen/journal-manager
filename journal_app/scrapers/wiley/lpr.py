# scrapers/rss/lpr.py - Laser & Photonics Reviews

from scrapers.wiley._base import WileyTOCScraper


class LprScraper(WileyTOCScraper):
    journal_id = "lpr"
    journal_name = "Laser & Photonics Reviews"
    journal_name_cn = "激光与光子学评论"
    code = "lpr"
    toc_id = "18638899"
    toc_domain = "onlinelibrary.wiley.com"
    list_url = "https://onlinelibrary.wiley.com/toc/18638899/current"


scraper = LprScraper()

if __name__ == "__main__":
    scraper.run_standalone()
