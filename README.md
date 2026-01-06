# Strava Recording Quality  
**Strava GPS Recording Quality & Geospatial Analysis**

Strava Recording Quality is a compact, end-to-end backend system built on top of the Strava API that focuses on the **recording, mapping, and geospatial analysis layer** of fitness tracking.

It ingests raw GPS streams from Strava activities, stores them in **PostgreSQL + PostGIS**, reconstructs tracks, and computes **interpretable recording-quality metrics** such as distance, max speed, GPS spikes, stops, and signal jitter.

The project is intentionally small but production-oriented and mirrors problems commonly encountered in live activity tracking, mapping, and applied ML systems.

---

## Why this project

Fitness activities are recorded under noisy real-world conditions:
- GPS jitter and signal loss
- teleport jumps (“spikes”)
- false or missing pauses
- irregular sampling intervals
- device variability

Before this data can be used for routing, mapping, or ML-driven insights, it must be **ingested correctly**, **stored in a geospatially native format**, and **analyzed for quality**.

Strava Recording Quality demonstrates this pipeline end-to-end.

---

## Features

### Strava OAuth authentication
- Secure login using Strava OAuth
- User access tokens stored in the database
- No tokens stored in source control

**Endpoints**
```
GET /auth/strava/login
GET /auth/strava/callback
```

---

### Activity metadata ingestion
- Syncs recent athlete activities
- Idempotent upserts into Postgres

**Endpoint**
```
POST /sync/activities
```

---

### Raw GPS stream ingestion (PostGIS)
- Fetches lat/lng/time/altitude streams from Strava
- Stores one row per GPS point
- Geometry stored as `POINT (SRID 4326)`
- Indexed with GiST for spatial queries

**Endpoint**
```
POST /activities/{activity_id}/ingest_streams
```

---

### Track reconstruction (GeoJSON)
- Rebuilds ordered LineStrings from raw points
- Suitable for visualization or downstream ML

**Endpoint**
```
GET /activities/{activity_id}/track
```

---

### Recording quality analysis
Computes interpretable metrics directly from GPS signals:
- GPS-derived distance
- maximum instantaneous speed
- spike (teleport jump) detection
- stop detection
- jitter score (signal stability proxy)

**Endpoint**
```
GET /activities/{activity_id}/quality
```

---

### Minimal demo UI
- Static Leaflet map
- Shows activity track + quality report

```
GET /static/demo.html
```

---

## Example output

```json
{
  "activity_id": 2,
  "sport_type": "Run",
  "distance_m_gps": 9968.43,
  "duration_s": 3886,
  "max_speed_kmh": 13.24,
  "spike_count": 0,
  "stop_segments": 0,
  "jitter_score": 0.24
}
```

## Architecture overview

**Backend**
- FastAPI
- SQLAlchemy + Alembic
- PostgreSQL + PostGIS
- GeoAlchemy2 + Shapely
- httpx (Strava API client)

**Design highlights**
- One row per recorded GPS point
- PostGIS-native geometry storage
- Idempotent ingestion
- Clean API boundaries between ingestion, geometry, and analytics

## Repository structure
```
strava-recording-quality/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   ├── integrations/
│   │   ├── models/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── schemas/
│   │   └── static/
│   │       └── demo.html
│   ├── alembic/
│   ├── alembic.ini
│   ├── requirements.txt
│   └── .env.example
├── infra/
│   └── docker-compose.yml
└── README.md
```

## Local setup

**Prerequisites**
- Docker + Docker Compose
- Python 3.11+
- Strava developer account

1) Start Postgres + PostGIS (from repo root):
```bash
docker compose -f infra/docker-compose.yml up -d
```

2) Backend environment:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3) Configure environment variables:
```bash
cp .env.example .env
```
Fill in:
- STRAVA_CLIENT_ID
- STRAVA_CLIENT_SECRET

In your Strava developer app settings:
- Authorization Callback Domain: 127.0.0.1
- Redirect URI: http://127.0.0.1:8000/auth/strava/callback

4) Run database migrations:
```bash
PYTHONPATH=. alembic upgrade head
```

5) Start the API:
```bash
uvicorn app.main:app --reload --port 8000
```
Swagger UI: http://127.0.0.1:8000/docs

## Typical usage flow

1) Authenticate with Strava (open in browser):
```
http://127.0.0.1:8000/auth/strava/login
```

2) Sync activities:
```bash
curl -X POST "http://127.0.0.1:8000/sync/activities?per_page=30"
```

3) Pick an activity:
```bash
curl "http://127.0.0.1:8000/activities?limit=5"
```

4) Ingest GPS streams:
```bash
curl -X POST "http://127.0.0.1:8000/activities/<id>/ingest_streams"
```

5) View results  
Track (GeoJSON):
```bash
curl "http://127.0.0.1:8000/activities/<id>/track"
```
Quality report:
```bash
curl "http://127.0.0.1:8000/activities/<id>/quality"
```

6) Demo map (open):
```
http://127.0.0.1:8000/static/demo.html
```
(You can change the hardcoded `activityId` in `demo.html`.)

## Design considerations
- PostGIS-native geometry enables accurate spatial analysis and indexing.
- Point-level storage preserves sampling irregularities and makes signal analysis explicit.
- Simple, interpretable metrics provide immediate product value and are easy to extend into ML models.
- Clear separation of concerns makes the system easy to evolve or scale.

## Possible extensions (out of scope by design)
- Sport-specific quality thresholds
- Kalman or spline smoothing
- Map matching to road graphs
- Streaming ingestion
- ML-based anomaly classification
