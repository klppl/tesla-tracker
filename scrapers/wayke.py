import time
import requests
from scrapers.base import BaseScraper

REQUEST_DELAY = 1.5  # seconds between pages
MAX_RETRIES = 3

SEARCH_URL = "https://www.wayke.se/api/search/vehicles"


class WaykeScraper(BaseScraper):
    name = "wayke.se"

    def _fetch_page(self, offset, hits):
        params = {
            "manufacturer": "Tesla",
            "hits": hits,
            "offset": offset,
        }
        for attempt in range(MAX_RETRIES):
            response = requests.get(SEARCH_URL, params=params, headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (compatible; TeslaTracker/1.0)",
            })
            if response.status_code == 429:
                wait = (attempt + 1) * 5
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            result = response.json()["documentList"]
            return result["documents"], result["numberOfHits"]
        response.raise_for_status()

    def fetch(self) -> list[dict]:
        page_size = 100
        offset = 0
        all_docs = []

        while True:
            docs, total = self._fetch_page(offset, page_size)
            if not docs:
                break
            all_docs.extend(docs)
            offset += len(docs)
            if offset >= total:
                break
            time.sleep(REQUEST_DELAY)

        documents = all_docs

        cars = []
        for doc in documents:
            car_id = doc.get("_id")
            if not car_id:
                continue

            # Extract image URL
            image_url = None
            featured = doc.get("featuredImage", {})
            files = featured.get("files", [])
            if files:
                formats = files[0].get("formats", [])
                for fmt in formats:
                    if fmt.get("format") == "800x":
                        image_url = fmt.get("jpeg")
                        break
                if not image_url and formats:
                    image_url = formats[0].get("jpeg")

            # Mileage: Wayke uses "mileage" field in km
            # odometerReading.unit can be "ScandinavianMile" but mileage field is in km
            mileage = doc.get("mileage")
            odometer = doc.get("odometerReading", {})
            if odometer.get("unit") == "ScandinavianMile" and mileage:
                mileage = mileage * 10  # Convert mil to km

            color = doc.get("properties", {}).get("colorName")

            cars.append({
                "id": car_id,
                "model": doc.get("modelSeries", "Unknown"),
                "version": doc.get("title", "").replace("Tesla ", ""),
                "year": doc.get("modelYear"),
                "price": doc.get("price"),
                "mileage": mileage,
                "created_at": doc.get("itemPublished"),
                "features": "",
                "image_url": image_url,
                "url": f"https://www.wayke.se/objekt/{car_id}",
                "color": color,
                "towbar": None,
                "winter_wheels": None,
                "battery_range": None,
                "source": self.name,
            })

        return cars
