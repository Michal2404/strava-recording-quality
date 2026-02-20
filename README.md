# Strava Recording Quality
[![CI](https://github.com/Michal2404/strava-recording-quality/actions/workflows/ci.yml/badge.svg)](https://github.com/Michal2404/strava-recording-quality/actions/workflows/ci.yml)

Strava Recording Quality is an end-to-end backend + web system for:
- ingesting Strava activities and GPS streams,
- storing point-level geospatial data in PostgreSQL/PostGIS,
- computing recording-quality metrics,
- and (currently in rebuild) evolving into a production ML classifier.

![UI screenshot](docs/demov2.png)

## Live Deployment
- App: [https://api.michalszczepanski.com/](https://api.michalszczepanski.com/)
- API docs: [https://api.michalszczepanski.com/docs](https://api.michalszczepanski.com/docs)
- Health: [https://api.michalszczepanski.com/health](https://api.michalszczepanski.com/health)

## Project Status (Rebuild in Progress)

### Implemented now
- Strava OAuth authentication and token persistence.
- Activity sync with pagination and filtering (`/sync/activities`).
- GPS stream ingestion to PostGIS point table (`/activities/{id}/ingest_streams`).
- GeoJSON outputs (`/track`, `/points.geojson`).
- Persisted activity quality metrics (`activity_quality_metrics`).
- Feature endpoint for analytics/ML-ready values (`/activities/{id}/features`).
- ML labeling foundation:
  - `activity_quality_labels` table
  - `POST /ml/activities/{activity_id}/label`
  - `GET /ml/labels`
- CI for backend lint + unit/integration tests.
- EC2 deployment with Docker Compose, Nginx TLS, and systemd startup.

### In progress now
- Converting quality analytics pipeline into a full applied ML system.
- Building persistent feature snapshots for reproducible training.
- Training/evaluation pipeline and model registry.
- Online inference endpoint and ML monitoring.

## Final Version Vision
The final version is a productionized **GPS Recording Quality Classifier** that:
1. trains models on labeled activity data,
2. evaluates them with explicit metrics and thresholds,
3. deploys an active model version,
4. serves predictions via API,
5. and monitors serving quality + data drift.

Expected final user flow:
1. Sync activities and ingest streams.
2. Compute and persist quality metrics/features.
3. Label activities (`good`/`bad` quality).
4. Train and register a model version.
5. Predict quality class for any activity.
6. Monitor model behavior over time.

## Architecture (Current)

```mermaid
flowchart LR
  UI["Web UI<br/>(React + Vite + Leaflet)"] -->|HTTPS| NGINX["Nginx<br/>(TLS + reverse proxy)"]
  NGINX --> API["FastAPI backend<br/>(Gunicorn + Uvicorn)"]
  API <--> STRAVA["Strava API<br/>(OAuth + activities + streams)"]
  API --> DB[("PostgreSQL + PostGIS<br/>users, activities, activity_points,<br/>activity_quality_metrics, activity_quality_labels")]
  CI["GitHub Actions CI"] --> API
  OBS["Structured logs + request IDs<br/>Optional Sentry"] --> API
```

## Architecture (Target Final ML Version)

```mermaid
flowchart LR
  UI["Web UI"] --> API["FastAPI API"]
  API --> DB[("PostgreSQL/PostGIS")]
  API --> REG["Model Registry Metadata<br/>(ml_models)"]
  API --> PRED["Prediction Store<br/>(activity_quality_predictions)"]
  DB --> FEAT["Feature Builder Service"]
  FEAT --> FEATTBL[("activity_ml_features")]
  FEATTBL --> TRAIN["Training + Evaluation Pipeline"]
  TRAIN --> ART["Model Artifacts"]
  ART --> API
  MON["Monitoring/Drift Jobs"] --> DB
  MON --> API
```

## Current Data Model

Core tables already in use:
- `users`
- `strava_tokens`
- `activities`
- `activity_points`
- `activity_quality_metrics`
- `activity_quality_labels`

Planned next ML tables:
- `activity_ml_features`
- `ml_models`
- `activity_quality_predictions`

## API Surface (Current)

### Auth
- `GET /auth/strava/login`
- `GET /auth/strava/callback`

### Ingestion
- `POST /sync/activities`
- `POST /activities/{activity_id}/ingest_streams`

### Analytics / Geospatial Outputs
- `GET /activities/`
- `GET /activities/{activity_id}/track`
- `GET /activities/{activity_id}/points.geojson`
- `GET /activities/{activity_id}/quality`
- `GET /activities/{activity_id}/features`

### ML Labeling (implemented in rebuild)
- `POST /ml/activities/{activity_id}/label`
- `GET /ml/labels`

## Local Development

### Prerequisites
- Docker + Docker Compose
- Python 3.12+
- Node 18+ (Node 20 recommended)
- Strava developer account

### 1) Start DB and Redis
```bash
docker compose -f infra/docker-compose.yml up -d db redis
```

### 2) Backend setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3) Environment config
```bash
cp .env.example .env
```

Set required values:
- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REDIRECT_URI` (local: `http://127.0.0.1:8000/auth/strava/callback`)
- `AUTH_SUCCESS_REDIRECT_URL` (local UI: `http://127.0.0.1:5173/`)

### 4) Apply migrations
```bash
PYTHONPATH=. alembic upgrade head
```

### 5) Run backend
```bash
uvicorn app.main:app --reload --port 8000
```

Swagger: `http://127.0.0.1:8000/docs`

### 6) Run web UI
```bash
cd ../web
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

## Quick Smoke Test

### Sync + ingest + inspect
```bash
curl -X POST "http://127.0.0.1:8000/sync/activities?per_page=30"
curl -X POST "http://127.0.0.1:8000/activities/2/ingest_streams"
curl "http://127.0.0.1:8000/activities/2/quality"
curl "http://127.0.0.1:8000/activities/2/features"
```

### ML labeling endpoints
```bash
curl -X POST "http://127.0.0.1:8000/ml/activities/2/label" \
  -H "Content-Type: application/json" \
  -d '{"label_bad": true, "label_source": "manual", "label_reason": "gps spikes", "label_confidence": 0.9, "created_by": "michal"}'

curl "http://127.0.0.1:8000/ml/labels?label_bad=true&label_source=manual"
```

## Testing

Run from `backend/`.

Unit tests:
```bash
PYTHONPATH=. pytest tests/unit -q
```

Integration tests (requires PostgreSQL + PostGIS):
```bash
TEST_DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/livemap_test PYTHONPATH=. pytest tests/integration -q
```

## CI

Workflow: `.github/workflows/ci.yml`
- Pull requests: backend lint + unit/integration tests
- Pushes to `main`: backend checks + backend image build

## Deployment and Operations
- EC2 runbook: `docs/deployment-ec2.md`
- Operations runbook: `docs/operations.md`

Production stack:
- Docker Compose services: `api`, `db`, `redis`
- Nginx reverse proxy with Let's Encrypt TLS
- systemd service (`srq-stack.service`) for reboot-safe startup

## Rebuild Roadmap (High Level)

1. Label storage and APIs (done).
2. Feature snapshot table + feature builder service.
3. Weak-label bootstrap and labeling workflow.
4. Model training + evaluation pipeline.
5. Model registry + active model selection.
6. Online prediction endpoint + prediction persistence.
7. Monitoring and drift checks.

## Notes
- The project is intentionally being rebuilt in increments, with working production behavior preserved at each step.
- Current functionality is stable for ingestion and analytics; ML classifier components are being added iteratively.
