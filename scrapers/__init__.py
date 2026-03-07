from scrapers.carla import CarlaScraper
from scrapers.wayke import WaykeScraper

# Register all scrapers here. Each must implement fetch() -> list[dict]
ALL_SCRAPERS = [
    CarlaScraper(),
    WaykeScraper(),
]
