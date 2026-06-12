# scrapers/rss/nanoph.py - Nanophotonics

from scrapers.wiley._base import WileyTOCScraper


class NanophScraper(WileyTOCScraper):
    journal_id = "nanoph"
    journal_name = "Nanophotonics"
    journal_name_cn = "纳米光子学"
    code = "nanoph"
    toc_id = "21928614"
    toc_domain = "onlinelibrary.wiley.com"
    list_url = "https://onlinelibrary.wiley.com/journal/21928614"


scraper = NanophScraper()

if __name__ == "__main__":
    scraper.run_standalone()
