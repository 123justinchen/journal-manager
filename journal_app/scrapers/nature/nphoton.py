# scrapers/nature/nphoton.py - Nature Photonics

from scrapers.nature._base import NatureBaseScraper

class NphotonScraper(NatureBaseScraper):
    journal_id = "nphoton"
    journal_name = "Nature Photonics"
    journal_name_cn = "自然光子学"
    code = "nphoton"
    nature_code = "nphoton"
    list_url = "https://www.nature.com/nphoton/volumes"

scraper = NphotonScraper()

if __name__ == "__main__":
    scraper.run_standalone()
