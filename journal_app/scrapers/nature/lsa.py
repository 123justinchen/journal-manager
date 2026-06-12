# scrapers/nature/lsa.py - Light: Science & Applications

from scrapers.nature._base import NatureBaseScraper


class LsaScraper(NatureBaseScraper):
    journal_id = "lsa"
    journal_name = "Light: Science & Applications"
    journal_name_cn = "光：科学与应用"
    code = "lsa"
    nature_code = "lsa"
    use_volume_navigation = False
    list_url = "https://www.nature.com/lsa/articles?type=article"


scraper = LsaScraper()

if __name__ == "__main__":
    scraper.run_standalone()
