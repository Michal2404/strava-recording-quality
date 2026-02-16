# Operations Runbook (SRQ-10)

This runbook describes the observability baseline for production operation.

## Structured logs

Backend logs are emitted as JSON to stdout/stderr with these fields:
- `timestamp`
- `level`
- `logger`
- `message`
- request metadata when applicable:
  - `request_id`
  - `method`
  - `path`
  - `query`
  - `status_code`
  - `duration_ms`
  - `client_ip`

Every API response includes `X-Request-ID`.

## Error diagnostics

Unhandled exceptions are logged at error level with stack traces and request context.

Client receives:
```json
{"detail":"Internal server error","request_id":"..."}
```

Use the `request_id` to find matching server logs.

## Optional Sentry

Enable Sentry with:
- `SENTRY_DSN`
- `SENTRY_TRACES_SAMPLE_RATE` (for example `0.1`)

If `SENTRY_DSN` is empty, Sentry is disabled.

## Useful commands on EC2

### systemd service state
```bash
systemctl status srq-stack.service --no-pager -l
```

### Tail backend container logs
```bash
cd /opt/strava-recording-quality
docker compose --env-file .env.deploy -f infra/docker-compose.yml logs -f api
```

### Recent backend errors only
```bash
cd /opt/strava-recording-quality
docker compose --env-file .env.deploy -f infra/docker-compose.yml logs --since=30m api | grep '\"level\":\"ERROR\"'
```

## Minimum dashboard/alerts checklist

Track these baseline signals:
- Host CPU utilization
- Host memory utilization
- API request latency (p50/p95)
- API error rate (5xx count)
- Container restarts (`api`, `db`)

AWS-first baseline:
- CloudWatch metrics for EC2 CPU/network/disk
- CloudWatch agent (optional) for memory/disk detail
- Alarm on sustained high CPU and repeated container restarts
