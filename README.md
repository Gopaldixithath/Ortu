# ORTU Fitness

A standalone health-and-fitness website for a small studio: a modern marketing
page, a **live class timetable**, flexible **memberships**, online **booking**
with hard capacity limits, a **1-hour cancellation cutoff**, and secure
**GoCardless Direct Debit** checkout for one-off and recurring payments.

This is a self-contained project. It does **not** depend on any other platform —
everything (frontend, API, database) runs together from this folder.

## Architecture

```
Browser ──► FastAPI (serves the built React site + JSON API) ──► PostgreSQL
                              │
                              └──► GoCardless (Direct Debit payments)
```

- **Frontend** — React 19 + Vite (`frontend/`). Built to static files and
  served by the API in production.
- **Backend** — FastAPI + SQLAlchemy (`backend/`). Booking rules, memberships,
  admin, and GoCardless integration.
- **Database** — PostgreSQL. Schema managed by Alembic migrations.
- **Packaging** — one Docker image (frontend built in, API serves it) plus a
  Postgres container, wired together by `docker-compose.yml`.

## Quick start (Docker — recommended)

Prerequisites: Docker Desktop.

```bash
cp .env.example .env        # edit values (a POSTGRES_PASSWORD is enough to start)
docker compose up --build   # builds the site, starts Postgres, runs migrations
```

Then open **http://localhost:8000**.

Add a starter timetable so the classes list is not empty:

```bash
docker compose exec web python seed.py
```

Stop with `docker compose down` (add `-v` to also wipe the database volume).

## Local development (without Docker)

Run the API and the frontend dev server separately.

**Backend** (needs a reachable Postgres; set `DATABASE_URL`):

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt
export DATABASE_URL=postgresql://ortu:pw@localhost:5432/ortu
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

**Frontend** (proxies `/api` to the backend on :8000):

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Postgres connection string (set automatically by compose). |
| `POSTGRES_PASSWORD` | Password for the bundled Postgres container. |
| `PORT` | Host port for the site (default `8000`). |
| `GOCARDLESS_ENVIRONMENT` | `sandbox` or `live`. |
| `GOCARDLESS_ACCESS_TOKEN` | GoCardless API token. Blank = payments disabled ("setup mode"). |
| `GOCARDLESS_WEBHOOK_ENDPOINT_SECRET` | Secret used to verify incoming GoCardless webhooks. |
| `ORTU_FITNESS_ADMIN_KEY` | Long random string; unlocks the studio admin panel. |
| `ORTU_FITNESS_PUBLIC_URL` | Public site URL for payment return links (blank locally). |

## Managing classes (studio admin)

1. Set `ORTU_FITNESS_ADMIN_KEY` to a long random value and restart.
2. On the site, footer → **Studio login**, enter that key.
3. Publish classes with a name, coach, capacity, location, and start/end time.
   Capacity is enforced live — a class cannot be overbooked, and it cannot be
   lowered below the number already booked.

## Enabling payments (GoCardless)

1. Create a GoCardless account and get a **sandbox** access token.
2. Set `GOCARDLESS_ACCESS_TOKEN`, `GOCARDLESS_ENVIRONMENT=sandbox`, and
   `ORTU_FITNESS_PUBLIC_URL` (your public address), then restart.
3. In the GoCardless dashboard, register the webhook endpoint
   `https://<your-domain>/api/gocardless/webhook` and put its signing secret in
   `GOCARDLESS_WEBHOOK_ENDPOINT_SECRET`.
4. Test a full join → pay → book flow in sandbox before switching to `live`.

## Deploying to a server

Any host with Docker (a small VPS is plenty):

```bash
# on the server
git clone <this-repo> ortu-fitness && cd ortu-fitness
cp .env.example .env      # set a strong POSTGRES_PASSWORD, ADMIN_KEY, GoCardless creds, PUBLIC_URL
docker compose up -d --build
docker compose exec web python seed.py   # optional: starter classes
```

Put it behind a reverse proxy (Caddy/Nginx) for HTTPS on your domain, pointing
at `127.0.0.1:${PORT}`. The migration runs automatically on every start.

## Booking rules (enforced server-side)

- A class can never exceed its capacity (checked inside a row-locked transaction).
- Online cancellation closes **60 minutes** before the class starts.
- Cancelling in time restores the class credit.
- Finite memberships (e.g. 4/8 classes) block booking once credits run out;
  unlimited memberships are only limited by their active date range.

## Project structure

```
.
├── docker-compose.yml        # Postgres + web app
├── .env.example              # configuration template
├── backend/
│   ├── Dockerfile            # builds frontend + Python runtime image
│   ├── entrypoint.sh         # waits for DB, migrates, starts uvicorn
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── migrations/           # Alembic (schema)
│   ├── seed.py               # starter timetable
│   └── app/
│       ├── main.py           # FastAPI app + static frontend serving
│       ├── db.py
│       ├── models.py         # 5 tables: members, memberships, sessions, bookings, webhook_events
│       ├── membership_plans.py
│       ├── booking_rules.py
│       ├── gocardless.py
│       └── routers/public_site.py   # all /api routes
└── frontend/                 # React + Vite site
    ├── src/App.jsx
    ├── src/styles.css
    └── src/assets/hero.png
```
