# Breathe ESG Internship Assignment

A Django REST + React prototype for ingesting realistic ESG activity data, normalizing it, and giving analysts a review-and-lock workflow before audit.

## What This Demonstrates

- Three realistic source shapes: SAP CSV, Green Button utility XML, and Concur-style travel JSON.
- Raw source records preserved separately from normalized ESG activity rows.
- Row-level failed and suspicious findings for analyst review.
- Scope 1/2/3 categorization, unit normalization, source tracking, tenant isolation, approval, locking, and audit export.

## Reviewer Access

Demo credentials after seeding:

- Email: `analyst@acme.example`
- Password: `BreatheDemo123!`
- Organization: `Acme Manufacturing`

## Local Setup

Start Postgres with Docker:

```bash
docker compose up -d db
```

Create and activate a Python virtual environment, then install dependencies:

```bash
pip install -r requirements.txt
python backend/manage.py migrate
python backend/manage.py seed_demo
python backend/manage.py runserver 127.0.0.1:8010
```

On this Windows workspace, you can also run:

```powershell
.\scripts\run_backend.ps1
```

Run the frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the API at `http://localhost:8010/api`. Override with `VITE_API_BASE_URL`.

## Deployment

The app is designed for Render with three resources:

- Web service: Django backend.
- Database: Render managed PostgreSQL.
- Static site: React frontend.
- Build command: `pip install -r requirements.txt && python backend/manage.py collectstatic --noinput && python backend/manage.py migrate`
- Start command: `gunicorn config.wsgi:application --chdir backend`

For the static site, set `VITE_API_BASE_URL` to the deployed backend API URL, for example `https://breathe-esg.onrender.com/api`.
For the backend, set `CORS_ALLOWED_ORIGINS` to the deployed frontend URL.

## Sample Files

Use the files in `samples/`:

- `sap_fuel_procurement.csv`
- `utility_green_button.xml`
- `travel_concur_itinerary.json`

## Reviewer Flow

1. Log in with the demo credentials.
2. Upload each sample file using its matching source card.
3. Review dashboard counts for received, failed, suspicious, pending, approved, and locked rows.
4. Open rows in the review queue to compare raw source payloads against normalized fields.
5. Approve clean or warning-only rows; reject failed rows or leave them visible as failed.
6. Lock approved rows and export the locked audit CSV.

## Assignment Documents

- [MODEL.md](MODEL.md)
- [DECISIONS.md](DECISIONS.md)
- [TRADEOFFS.md](TRADEOFFS.md)
- [SOURCES.md](SOURCES.md)
