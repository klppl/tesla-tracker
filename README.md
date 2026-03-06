# Tesla Tracker

Analysverktyg för begagnade Teslor på den svenska marknaden. Scrapar annonser från [Carla.se](https://www.carla.se) och visar pris- och miltrender i en interaktiv dashboard.

## Funktioner

- **Scraper** – Hämtar aktuella Tesla-annonser via Carlas Algolia-API
- **Dashboard** – Visar pris vs miltal per modell, snittpris per årsmodell och dagliga annonstillägg
- **Fynd-radar** – Scatter-diagram där du kan klicka på punkter för att öppna annonsen direkt

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

Hämtar annonser och sparar dem i en lokal SQLite-databas (`tesla_cars.db`):

```bash
uv run scraper.py
```

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
├── app.py           # Flask-app (--server) och statisk generator (--static)
├── database.py      # Databasschema och anslutning (SQLite)
├── scraper.py       # Hämtar annonser från Carla.se
├── templates/
│   └── index.html   # Dashboard-vy med Chart.js-diagram
└── tesla_cars.db    # SQLite-databas (skapas automatiskt)
```

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
- **Algolia API** (Carla.se) som datakälla
