# scrapers/ieee/mwcl.py — IEEE Microwave and Wireless Components Letters (DrissionPage TOC)
from scrapers.ieee._base import ieee_browser_scrape
from scrapers.base import BaseScraper

class _MWCLScraper(BaseScraper):
    journal_id = "mwcl"
    journal_name = "IEEE Microwave and Wireless Components Letters"
    journal_name_cn = "IEEE 微波与无线组件快报"
    publisher = "IEEE"
    journal_type = "ieee"
    code = "mwcl"
    punumber = "7260"
    list_url = "https://ieeexplore.ieee.org/xpl/mostRecentIssue.jsp?punumber=7260"

    def scrape(self):
        return ieee_browser_scrape(self)

scraper = _MWCLScraper()
if __name__ == "__main__":
    scraper.run_standalone()
