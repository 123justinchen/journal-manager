# scrapers/ieee/awpl.py — IEEE Antennas and Wireless Propagation Letters (DrissionPage TOC)
from scrapers.ieee._base import ieee_browser_scrape
from scrapers.base import BaseScraper

class _AWPLScraper(BaseScraper):
    journal_id = "awpl"
    journal_name = "IEEE Antennas and Wireless Propagation Letters"
    journal_name_cn = "IEEE 天线与无线传播快报"
    publisher = "IEEE"
    journal_type = "ieee"
    code = "awpl"
    punumber = "7727"
    list_url = "https://ieeexplore.ieee.org/xpl/mostRecentIssue.jsp?punumber=7727"

    def scrape(self):
        return ieee_browser_scrape(self)

scraper = _AWPLScraper()
if __name__ == "__main__":
    scraper.run_standalone()
