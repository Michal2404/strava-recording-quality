# Benchmark Snapshot

Date: 2026-02-16  
Environment: local Docker runtime (`infra/docker-compose.yml`) on development machine  
Database: `livemap` (PostgreSQL/PostGIS)

## Data volume

| Metric | Value | Method |
| --- | ---: | --- |
| Activities processed | 351 | `SELECT COUNT(*) FROM activities;` |
| Point-level rows ingested | 9,275 | `SELECT COUNT(*) FROM activity_points;` |

## Endpoint latency

Method:
- 5 warm-up requests per endpoint
- 50 measured requests per endpoint
- metric shown: median (p50) and p95 of `curl` `time_total`

| Endpoint | Median latency (ms) | p95 latency (ms) |
| --- | ---: | ---: |
| `GET /health` | 1.27 | 1.50 |
| `GET /activities/?limit=50` | 3.59 | 4.30 |
| `GET /activities/2/quality` | 3.28 | 3.94 |
| `GET /activities/2/points.geojson` | 15.47 | 36.20 |

## Reproduce commands

### Data volume
```bash
docker exec infra-db-1 psql -U app -d livemap -t -A -c "SELECT COUNT(*) FROM activities;"
docker exec infra-db-1 psql -U app -d livemap -t -A -c "SELECT COUNT(*) FROM activity_points;"
```

### Latency sampling
```bash
benchmark_endpoint() {
  local name="$1"
  local url="$2"
  local samples=50
  for _ in $(seq 1 5); do
    curl -sS -o /dev/null "$url"
  done
  local values
  values=$(mktemp)
  for _ in $(seq 1 "$samples"); do
    curl -sS -o /dev/null -w '%{time_total}\n' "$url" >> "$values"
  done
  local median p95
  median=$(sort -n "$values" | awk 'NR==25{a=$1} NR==26{b=$1} END{printf "%.6f", (a+b)/2}')
  p95=$(sort -n "$values" | awk 'NR==48{printf "%.6f", $1}')
  rm -f "$values"
  printf "%s median=%s p95=%s\n" "$name" "$median" "$p95"
}

benchmark_endpoint health "http://127.0.0.1:8000/health"
benchmark_endpoint activities_list "http://127.0.0.1:8000/activities/?limit=50"
benchmark_endpoint quality "http://127.0.0.1:8000/activities/2/quality"
benchmark_endpoint points_geojson "http://127.0.0.1:8000/activities/2/points.geojson"
```
