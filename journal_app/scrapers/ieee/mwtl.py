# scrapers/ieee/mwtl.py — IEEE Microwave and Wireless Technology Letters (DrissionPage TOC)
from scrapers.ieee._base import ieee_browser_scrape
from scrapers.base import BaseScraper

class _MWTLScraper(BaseScraper):
    journal_id = "mwtl"
    journal_name = "IEEE Microwave and Wireless Technology Letters"
    journal_name_cn = "IEEE 微波与无线技术快报"
    publisher = "IEEE"
    journal_type = "ieee"
    code = "mwtl"
    punumber = "7260"
    list_url = "https://ieeexplore.ieee.org/xpl/mostRecentIssue.jsp?punumber=7260"

    def scrape(self):
        return ieee_browser_scrape(self)

scraper = _MWTLScraper()
if __name__ == "__main__":
    scraper.run_standalone()
