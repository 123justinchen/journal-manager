# scrapers/rss/ole.py - Optics and Lasers in Engineering

from scrapers.elsevier._base import ElsevierBaseScraper


class OleScraper(ElsevierBaseScraper):
    journal_id = "ole"
    journal_name = "Optics and Lasers in Engineering"
    journal_name_cn = "光学与激光工程"
    code = "ole"
    journal_url = "https://www.sciencedirect.com/journal/optics-and-lasers-in-engineering"
    list_url = journal_url


scraper = OleScraper()

if __name__ == "__main__":
    scraper.run_standalone()
