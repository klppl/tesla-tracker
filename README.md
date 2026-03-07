# Tesla Tracker

Analysverktyg för begagnade Teslor på den svenska marknaden. Scrapar annonser från [Carla.se](https://www.carla.se) och [Wayke.se](https://www.wayke.se), lagrar data i SQLite och visar en interaktiv dashboard med pris- och marknadstrender.

## Funktioner

- **Multi-scraper** – Hämtar annonser från Carla.se (Algolia API) och Wayke.se (intern sök-API), med full paginering och rate limiting
- **Fynd-radar** – Scatter-diagram (pris vs miltal) för alla modeller. Klicka på en punkt för att öppna annonsen. "Gyllene bilen" markeras med en guldstjärna (linjär regression hittar mest underprissatta bilen)
- **Sammanfattning** – Antal aktiva bilar per modell och datakälla
- **Prisutveckling** – Snitt- och medianpris per modell över tid (dagliga snapshots)
- **Marknadstrender** – Tid på marknaden, sålda bilar, kr/mil-beräkning
- **Utrustningsanalys** – Priseffekt av dragkrok, vinterdäck m.m.
- **Färgstatistik** – Snittpris per färg
- **Värdeminskningskurva** – Pris per ålder per modell
- **Köp-/säljtiming** – Annonsfördelning per veckodag och månad
- **Prisprediktering** – Linjär extrapolering 90 dagar framåt
- **Automatisk daglig uppdatering** – GitHub Actions kör scraper + statisk build varje dag kl 06:00 UTC

## Kom igång

### 1. Installera uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Skapa virtualenv och installera beroenden

```bash
uv venv
source .venv/bin/activate
uv pip install flask requests
```

### 3. Kör scrapern

Hämtar alla Tesla-annonser från samtliga källor och sparar i en lokal SQLite-databas (`tesla_cars.db`):

```bash
uv run scraper.py
```

Scrapern hämtar alla sidor automatiskt med 1,5 sekunders fördröjning mellan requests och exponentiell backoff vid rate limiting (HTTP 429).

### 4. Starta dashboarden

**Alternativ A – Lokal server:**

```bash
uv run app.py --server
```

Öppna [http://localhost:5000](http://localhost:5000) i webbläsaren.

**Alternativ B – Generera statisk sida:**

```bash
uv run app.py --static
```

Skapar `public/index.html` som kan öppnas direkt i webbläsaren eller hostas var som helst.

## Projektstruktur

```
├── app.py              # Flask-app (--server) och statisk generator (--static)
├── database.py         # Databasschema och anslutning (SQLite)
├── scraper.py          # Orkestrator: kör alla scrapers, sparar data, tar snapshots
├── scrapers/
│   ├── __init__.py     # Scraper-registry (ALL_SCRAPERS)
│   ├── base.py         # BaseScraper – gemensamt bilformat
│   ├── carla.py        # Carla.se via Algolia API
│   └── wayke.py        # Wayke.se via intern sök-API
├── templates/
│   └── index.html      # Dashboard med Chart.js-diagram
├── public/
│   └── index.html      # Genererad statisk sida
├── tesla_cars.db       # SQLite-databas (skapas automatiskt)
└── .github/workflows/
    └── scrape-and-build.yml  # Daglig CI: scrape + static build
```

## Lägga till en ny datakälla

1. Skapa en ny fil i `scrapers/`, t.ex. `scrapers/blocket.py`
2. Skapa en klass som ärver `BaseScraper` och implementera `fetch() -> list[dict]`
3. Returnera bilar i det gemensamma formatet (se `scrapers/base.py` för alla fält)
4. Registrera scrapern i `scrapers/__init__.py` genom att lägga till den i `ALL_SCRAPERS`

## Hosting med Cloudflare Pages

Sidan är helt statisk (`public/index.html`) och kan hostas gratis via Cloudflare Pages.

### Setup

1. Gå till [Cloudflare Dashboard](https://dash.cloudflare.com/) → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**
2. Välj ditt GitHub-repo
3. Ställ in:
   - **Build command**: _(lämna tomt)_
   - **Build output directory**: `public`
4. Klicka **Save and Deploy**

GitHub Actions-workflowen genererar `public/index.html` dagligen och committar till repot. Cloudflare Pages plockar upp ändringen automatiskt vid varje push.

### Eget domännamn (valfritt)

Under **Pages** → ditt projekt → **Custom domains** → lägg till din domän. Cloudflare sköter SSL automatiskt.

## Teknikstack

- **Python 3** med Flask
- **SQLite** för lokal lagring
- **Chart.js** för diagram
- **Algolia API** (Carla.se) och **Wayke intern API** som datakällor
- **GitHub Actions** för daglig automatisering
- **Cloudflare Pages** för hosting
