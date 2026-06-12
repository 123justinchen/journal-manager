# scrapers/ieee/thz.py — IEEE Transactions on Terahertz Science and Technology (DrissionPage TOC)
from scrapers.ieee._base import ieee_browser_scrape
from scrapers.base import BaseScraper

class _THZScraper(BaseScraper):
    journal_id = "thz"
    journal_name = "IEEE Transactions on Terahertz Science and Technology"
    journal_name_cn = "IEEE 太赫兹科学与技术汇刊"
    publisher = "IEEE"
    journal_type = "ieee"
    code = "thz"
    punumber = "5503871"
    list_url = "https://ieeexplore.ieee.org/xpl/mostRecentIssue.jsp?punumber=5503871"

    def scrape(self):
        return ieee_browser_scrape(self)

scraper = _THZScraper()
if __name__ == "__main__":
    scraper.run_standalone()
