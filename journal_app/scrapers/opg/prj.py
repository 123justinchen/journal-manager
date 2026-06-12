# scrapers/opg/prj.py - Photonics Research

from scrapers.opg._base import OPGBaseScraper

class PrjScraper(OPGBaseScraper):
    journal_id = "prj"
    journal_name = "Photonics Research"
    journal_name_cn = "光子学研究"
    code = "prj"
    list_url = "https://opg.optica.org/prj/issue.cfm"

scraper = PrjScraper()

if __name__ == "__main__":
    scraper.run_standalone()
