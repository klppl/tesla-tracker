import time
import requests
from scrapers.base import BaseScraper

REQUEST_DELAY = 1.5  # seconds between pages
MAX_RETRIES = 3

API_URL = "https://izs3uhkhl4-dsn.algolia.net/1/indexes/*/queries"
API_PARAMS = {
    "x-algolia-agent": "Algolia for JavaScript (4.25.2)",
    "x-algolia-application-id": "IZS3UHKHL4",
    "x-algolia-api-key": "05ebd9cb812d1c6ebe07ab6de7dc28bb",
}


def _clean_features(badges):
    if not badges:
        return ""
    if isinstance(badges, list):
        return ", ".join([str(b) for b in badges])
    return str(badges)


class CarlaScraper(BaseScraper):
    name = "carla.se"

    def _fetch_page(self, offset, length):
        payload = {
            "requests": [{
                "indexName": "new_created_at_desc",
                "params": f"filters=manufacturer%3A%22Tesla%22&offset={offset}&length={length}",
            }]
        }
        for attempt in range(MAX_RETRIES):
            response = requests.post(API_URL, params=API_PARAMS, json=payload)
            if response.status_code == 429:
                wait = (attempt + 1) * 5
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()["results"][0]["hits"]
        response.raise_for_status()

    def fetch(self) -> list[dict]:
        page_size = 50
        offset = 0
        all_hits = []

        while True:
            hits = self._fetch_page(offset, page_size)
            if not hits:
                break
            all_hits.extend(hits)
            if len(hits) < page_size:
                break
            offset += page_size
            time.sleep(REQUEST_DELAY)

        cars = []
        for car in all_hits:
            car_id = car.get("registrationNumber") or car.get("objectID")
            if not car_id:
                continue

            object_id = car.get("objectID", "")
            main_photo = car.get("mainPhoto")
            image_url = main_photo.get("url") if isinstance(main_photo, dict) else main_photo

            cars.append({
                "id": car_id,
                "model": car.get("model", "Unknown"),
                "version": car.get("version", ""),
                "year": car.get("modelYear"),
                "price": car.get("retailPrice"),
                "mileage": car.get("mileage"),
                "created_at": car.get("createdAt"),
                "features": _clean_features(car.get("badges", [])),
                "image_url": image_url,
                "url": f"https://www.carla.se/bil/{object_id}",
                "color": car.get("color"),
                "towbar": car.get("towbarAvailability"),
                "winter_wheels": car.get("winterWheelsTreadType"),
                "battery_range": car.get("batteryRange"),
                "source": self.name,
            })

        return cars
