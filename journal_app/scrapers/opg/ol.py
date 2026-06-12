# scrapers/opg/ol.py - Optics Letters

from scrapers.opg._base import OPGBaseScraper

class OlScraper(OPGBaseScraper):
    journal_id = "ol"
    journal_name = "Optics Letters"
    journal_name_cn = "光学快讯"
    code = "ol"
    list_url = "https://opg.optica.org/ol/issue.cfm"

scraper = OlScraper()

if __name__ == "__main__":
    scraper.run_standalone()
