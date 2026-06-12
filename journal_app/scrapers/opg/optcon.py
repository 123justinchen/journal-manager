# scrapers/opg/optcon.py - Optics Continuum

from scrapers.opg._base import OPGBaseScraper

class OptconScraper(OPGBaseScraper):
    journal_id = "optcon"
    journal_name = "Optics Continuum"
    journal_name_cn = "光学连续"
    code = "optcon"
    list_url = "https://opg.optica.org/optcon/issue.cfm"

scraper = OptconScraper()

if __name__ == "__main__":
    scraper.run_standalone()
