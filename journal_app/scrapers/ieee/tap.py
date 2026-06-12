# scrapers/ieee/tap.py — IEEE Transactions on Antennas and Propagation (DrissionPage TOC)
from scrapers.ieee._base import ieee_browser_scrape
from scrapers.base import BaseScraper

class _TAPScraper(BaseScraper):
    journal_id = "tap"
    journal_name = "IEEE Transactions on Antennas and Propagation"
    journal_name_cn = "IEEE 天线与传播汇刊"
    publisher = "IEEE"
    journal_type = "ieee"
    code = "tap"
    punumber = "8"
    list_url = "https://ieeexplore.ieee.org/xpl/mostRecentIssue.jsp?punumber=8"

    def scrape(self):
        return ieee_browser_scrape(self)

scraper = _TAPScraper()
if __name__ == "__main__":
    scraper.run_standalone()
