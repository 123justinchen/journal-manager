# scrapers/opg/aop.py - Advances in Optics and Photonics

from scrapers.opg._base import OPGBaseScraper

class AopScraper(OPGBaseScraper):
    journal_id = "aop"
    journal_name = "Advances in Optics and Photonics"
    journal_name_cn = "光学与光子学进展"
    code = "aop"
    list_url = "https://opg.optica.org/aop/issue.cfm"

scraper = AopScraper()

if __name__ == "__main__":
    scraper.run_standalone()
