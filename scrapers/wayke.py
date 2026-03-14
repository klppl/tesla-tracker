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
        skipped = 0
        for doc in documents:
            car_id = doc.get("_id")
            if not car_id:
                continue

            # Skip leasing listings – they have no real purchase price
            title = doc.get("title", "").lower()
            if "leasing" in title:
                skipped += 1
                continue

            # Skip listings with no price or zero price
            price = doc.get("price")
            if not price or price <= 0:
                skipped += 1
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

            # Mileage: Wayke "mileage" field is always in Scandinavian mil.
            # odometerReading.value is in the unit specified by odometerReading.unit.
            # Use odometerReading when available (more reliable), fall back to mileage * 10.
            odometer = doc.get("odometerReading", {})
            if odometer.get("unit") == "Kilometer" and odometer.get("value"):
                mileage = odometer["value"]
            else:
                mileage = doc.get("mileage")
                if mileage:
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

        if skipped:
            print(f"  Wayke: skipped {skipped} leasing/no-price listings")
        return cars
