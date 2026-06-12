# scrapers/rss/aom.py - Advanced Optical Materials

from scrapers.wiley._base import WileyTOCScraper


class AomScraper(WileyTOCScraper):
    journal_id = "aom"
    journal_name = "Advanced Optical Materials"
    journal_name_cn = "先进光学材料"
    code = "aom"
    toc_id = "21951071"
    toc_domain = "advanced.onlinelibrary.wiley.com"
    list_url = "https://advanced.onlinelibrary.wiley.com/toc/21951071/current"


scraper = AomScraper()

if __name__ == "__main__":
    scraper.run_standalone()
