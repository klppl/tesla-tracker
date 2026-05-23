class BaseScraper:
    """Base class for all scrapers. Each source implements fetch()
    which returns a list of cars in a common format:

    {
        "id": str,           # Unique identifier (reg number or listing ID)
        "model": str,        # e.g. "Model 3"
        "version": str,      # e.g. "Long Range AWD"
        "year": int,
        "price": int,        # SEK
        "mileage": int,      # km (not mil)
        "created_at": str,   # ISO timestamp
        "features": str,     # Comma-separated
        "image_url": str,
        "url": str,          # Link to listing
        "color": str | None,
        "towbar": str | None,
        "winter_wheels": str | None,
        "battery_range": int | None,  # km
        "source": str,       # e.g. "carla.se"
    }
    """

    name: str = "base"

    # Set to False by fetch() when pagination ends early due to an error,
    # so the orchestrator knows the result set may be incomplete and skips
    # removal reconciliation for this source (avoids false "sold" flags).
    last_fetch_complete: bool = True

    def fetch(self) -> list[dict]:
        raise NotImplementedError
