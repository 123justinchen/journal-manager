# scrapers/opg/col.py - Chinese Optics Letters

from scrapers.opg._base import OPGBaseScraper

class ColScraper(OPGBaseScraper):
    journal_id = "col"
    journal_name = "Chinese Optics Letters"
    journal_name_cn = "中国光学快报"
    code = "col"
    list_url = "https://opg.optica.org/col/issue.cfm"

scraper = ColScraper()

if __name__ == "__main__":
    scraper.run_standalone()
