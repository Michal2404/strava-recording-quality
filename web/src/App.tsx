import { useEffect, useMemo, useRef, useState } from 'react'
import type { Feature, GeoJsonObject, LineString } from 'geojson'
import L from 'leaflet'
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet'
import './App.css'

type Activity = {
  id: number
  strava_activity_id: number
  name?: string | null
  sport_type?: string | null
  start_date?: string | null
  distance_m?: number | null
  moving_time_s?: number | null
  elevation_gain_m?: number | null
}

type TrackFeature = Feature<
  LineString | null,
  {
    activity_id: number
    name?: string | null
    sport_type?: string | null
    point_count?: number
    start_date?: string | null
  }
>

type QualityReport = {
  activity_id: number
  name?: string | null
  sport_type?: string | null
  point_count: number
  duration_s: number
  distance_m_gps: number
  max_speed_mps: number
  max_speed_kmh: number
  spike_count: number
  stopped_time_s: number
  stop_segments: number
  jitter_score: number
}

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

const formatDuration = (totalSeconds?: number | null) => {
  if (!totalSeconds && totalSeconds !== 0) return '—'
  const hours = Math.floor(totalSeconds / 3600)
  const mins = Math.floor((totalSeconds % 3600) / 60)
  const secs = totalSeconds % 60
  if (hours > 0) return `${hours}h ${mins}m`
  return `${mins}m ${String(secs).padStart(2, '0')}s`
}

const formatDistance = (meters?: number | null) => {
  if (!meters && meters !== 0) return '—'
  return `${(meters / 1000).toFixed(2)} km`
}

const formatDate = (value?: string | null) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const getErrorMessage = (error: unknown) =>
  error instanceof Error ? error.message : 'Something went wrong'

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? 'GET').toUpperCase()
  const headers: HeadersInit = {
    ...(init?.headers ?? {}),
  }
  if (method !== 'GET' && method !== 'HEAD' && !('Content-Type' in headers)) {
    headers['Content-Type'] = 'application/json'
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  })

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const data = await response.json()
      if (data?.detail) detail = data.detail
    } catch {
      // ignore parsing errors
    }
    throw new ApiError(detail, response.status)
  }

  return (await response.json()) as T
}

function FitBounds({ feature }: { feature: TrackFeature | null }) {
  const map = useMap()

  useEffect(() => {
    if (!feature?.geometry) return
    const layer = L.geoJSON(feature as unknown as GeoJsonObject)
    const bounds = layer.getBounds()
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [40, 40] })
    }
  }, [feature, map])

  return null
}

function App() {
  const [activities, setActivities] = useState<Activity[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [listLoading, setListLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [ingesting, setIngesting] = useState(false)
  const [track, setTrack] = useState<TrackFeature | null>(null)
  const [quality, setQuality] = useState<QualityReport | null>(null)
  const [trackError, setTrackError] = useState<string | null>(null)
  const [qualityError, setQualityError] = useState<string | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [perPage, setPerPage] = useState(30)
  const [onlyRuns, setOnlyRuns] = useState(true)
  const [message, setMessage] = useState<string | null>(null)
  const autoIngestedIds = useRef<Set<number>>(new Set())

  const selectedActivity = useMemo(
    () => activities.find((activity) => activity.id === selectedId) ?? null,
    [activities, selectedId],
  )

  const loadActivities = async () => {
    setListLoading(true)
    setMessage(null)
    try {
      const data = await apiFetch<Activity[]>('/activities/?limit=50')
      setActivities(data)
      if (!selectedId && data.length > 0) {
        setSelectedId(data[0].id)
      }
    } catch (error) {
      setMessage(`Could not load activities. ${getErrorMessage(error)}`)
    } finally {
      setListLoading(false)
    }
  }

  const loadDetails = async (
    activityId: number,
    options?: { skipAutoIngest?: boolean },
  ) => {
    setDetailLoading(true)
    setTrackError(null)
    setQualityError(null)
    setTrack(null)
    setQuality(null)

    const [trackResult, qualityResult] = await Promise.allSettled([
      apiFetch<TrackFeature>(`/activities/${activityId}/track`),
      apiFetch<QualityReport>(`/activities/${activityId}/quality`),
    ])

    const isMissingPoints = (error: unknown) =>
      error instanceof ApiError &&
      error.status === 404 &&
      /ingest streams first|not enough points|no points found/i.test(error.message)

    const needsIngest =
      (trackResult.status === 'rejected' && isMissingPoints(trackResult.reason)) ||
      (qualityResult.status === 'rejected' && isMissingPoints(qualityResult.reason))

    if (needsIngest && !options?.skipAutoIngest && !autoIngestedIds.current.has(activityId)) {
      autoIngestedIds.current.add(activityId)
      setMessage('Auto-ingesting streams for this activity…')
      try {
        await apiFetch<{ ok: boolean; points: number }>(
          `/activities/${activityId}/ingest_streams`,
          { method: 'POST' },
        )
        setMessage('Streams ingested automatically.')
      } catch (error) {
        setMessage(`Auto-ingest failed. ${getErrorMessage(error)}`)
      }
      await loadDetails(activityId, { skipAutoIngest: true })
      return
    }

    if (trackResult.status === 'fulfilled') {
      setTrack(trackResult.value)
    } else {
      setTrackError(getErrorMessage(trackResult.reason))
    }

    if (qualityResult.status === 'fulfilled') {
      setQuality(qualityResult.value)
    } else {
      setQualityError(getErrorMessage(qualityResult.reason))
    }

    setDetailLoading(false)
  }

  const handleSync = async () => {
    setSyncing(true)
    setMessage(null)
    try {
      const params = new URLSearchParams({
        per_page: String(perPage),
      })
      if (onlyRuns) {
        params.set('sport_type', 'Run')
      }
      const result = await apiFetch<{ ok: boolean; count: number }>(
        `/sync/activities?${params.toString()}`,
        { method: 'POST' },
      )
      setMessage(
        onlyRuns
          ? `Synced ${result.count} run activities.`
          : `Synced ${result.count} activities.`,
      )
      await loadActivities()
    } catch (error) {
      setMessage(`Sync failed. ${getErrorMessage(error)}`)
    } finally {
      setSyncing(false)
    }
  }

  const handleIngest = async () => {
    if (!selectedId) return
    setIngesting(true)
    setMessage(null)
    try {
      await apiFetch<{ ok: boolean; points: number }>(
        `/activities/${selectedId}/ingest_streams`,
        { method: 'POST' },
      )
      setMessage('Streams ingested. Loading track and quality…')
      await loadDetails(selectedId)
    } catch (error) {
      setMessage(`Ingest failed. ${getErrorMessage(error)}`)
    } finally {
      setIngesting(false)
    }
  }

  useEffect(() => {
    void loadActivities()
  }, [])

  useEffect(() => {
    if (!selectedId) return
    void loadDetails(selectedId)
  }, [selectedId])

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="eyebrow">Strava Recording Quality</div>
          <h1>Activity Control Room</h1>
          <p>
            Ingest Strava GPS streams, reconstruct the track, and inspect quality
            metrics in one place.
          </p>
        </div>
        <div className="actions">
          <a className="btn ghost" href="/auth/strava/login">
            Connect with Strava
          </a>
          <div className="sync-group">
            <label htmlFor="per-page">Per page</label>
            <input
              id="per-page"
              type="number"
              min={5}
              max={50}
              value={perPage}
              onChange={(event) => {
                const value = Number(event.target.value)
                if (!Number.isFinite(value)) return
                const clamped = Math.min(50, Math.max(5, value))
                setPerPage(clamped)
              }}
            />
            <label className="filter-toggle">
              <input
                type="checkbox"
                checked={onlyRuns}
                onChange={(event) => setOnlyRuns(event.target.checked)}
              />
              Only runs
            </label>
            <button className="btn primary" onClick={handleSync} disabled={syncing}>
              {syncing ? 'Syncing…' : 'Sync activities'}
            </button>
          </div>
        </div>
      </header>

      <div className="layout">
        <aside className="panel sidebar">
          <div className="panel-header">
            <div>
              <h2>Activities</h2>
              <p>{listLoading ? 'Loading latest list…' : `${activities.length} synced`}</p>
            </div>
            <button className="btn subtle" onClick={loadActivities} disabled={listLoading}>
              Refresh
            </button>
          </div>
          <div className="activity-list">
            {activities.length === 0 && !listLoading ? (
              <div className="empty-state">
                <strong>No activities yet.</strong>
                <span>Connect with Strava, then sync to pull recent workouts.</span>
              </div>
            ) : (
              activities.map((activity) => (
                <button
                  key={activity.id}
                  className={`activity-card ${activity.id === selectedId ? 'active' : ''}`}
                  onClick={() => setSelectedId(activity.id)}
                >
                  <div className="activity-title">{activity.name || 'Untitled activity'}</div>
                  <div className="activity-meta">
                    <span>{activity.sport_type || 'Unknown'}</span>
                    <span>#{activity.id}</span>
                  </div>
                  <div className="activity-meta">
                    <span>{formatDate(activity.start_date)}</span>
                  </div>
                  <div className="activity-stats">
                    <span>{formatDistance(activity.distance_m)}</span>
                    <span>{formatDuration(activity.moving_time_s)}</span>
                    <span>
                      {activity.elevation_gain_m
                        ? `${activity.elevation_gain_m.toFixed(0)} m`
                        : '—'}
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>
        </aside>

        <main className="panel map-panel">
          <div className="panel-header">
            <div>
              <h2>Track</h2>
              <p>{selectedActivity?.name || 'Pick an activity to inspect its track.'}</p>
            </div>
            <div className="status">
              {detailLoading ? (
                <span className="chip">Loading track…</span>
              ) : trackError ? (
                <span className="chip warning">{trackError}</span>
              ) : track?.geometry ? (
                <span className="chip success">Track ready</span>
              ) : (
                <span className="chip">No track yet</span>
              )}
            </div>
          </div>

          <div className="map-shell">
            <MapContainer center={[52.52, 13.29]} zoom={12} className="map">
              <TileLayer
                attribution="&copy; OpenStreetMap contributors"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              {track?.geometry && (
                <GeoJSON
                  data={track as unknown as GeoJsonObject}
                  style={{
                    color: '#31c48d',
                    weight: 4,
                    opacity: 0.9,
                  }}
                />
              )}
              <FitBounds feature={track} />
            </MapContainer>
            {!track?.geometry && (
              <div className="map-overlay">
                <h3>No track data yet</h3>
                <p>Ingest the activity streams to build the GPS line.</p>
              </div>
            )}
          </div>
        </main>

        <section className="panel detail-panel">
          <div className="panel-header">
            <div>
              <h2>Quality</h2>
              <p>{selectedActivity?.sport_type || 'Waiting for activity selection'}</p>
            </div>
            <button
              className="btn primary"
              onClick={handleIngest}
              disabled={!selectedId || ingesting}
            >
              {ingesting ? 'Ingesting…' : 'Ingest streams'}
            </button>
          </div>

          {message && <div className="notice">{message}</div>}

          {quality ? (
            <div className="metrics">
              <div className="metric">
                <span>Distance (GPS)</span>
                <strong>{formatDistance(quality.distance_m_gps)}</strong>
              </div>
              <div className="metric">
                <span>Duration</span>
                <strong>{formatDuration(quality.duration_s)}</strong>
              </div>
              <div className="metric">
                <span>Max speed</span>
                <strong>{quality.max_speed_kmh.toFixed(1)} km/h</strong>
              </div>
              <div className="metric">
                <span>Spike count</span>
                <strong>{quality.spike_count}</strong>
              </div>
              <div className="metric">
                <span>Stop segments</span>
                <strong>{quality.stop_segments}</strong>
              </div>
              <div className="metric">
                <span>Jitter score</span>
                <strong>{quality.jitter_score.toFixed(2)}</strong>
              </div>
              <div className="metric">
                <span>Stopped time</span>
                <strong>{formatDuration(quality.stopped_time_s)}</strong>
              </div>
              <div className="metric">
                <span>Point count</span>
                <strong>{quality.point_count}</strong>
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <strong>Quality report unavailable.</strong>
              <span>{qualityError ?? 'Ingest streams to compute metrics.'}</span>
            </div>
          )}

          <div className="detail-card">
            <h3>Activity metadata</h3>
            {selectedActivity ? (
              <dl>
                <div>
                  <dt>Strava ID</dt>
                  <dd>{selectedActivity.strava_activity_id}</dd>
                </div>
                <div>
                  <dt>Start</dt>
                  <dd>{formatDate(selectedActivity.start_date)}</dd>
                </div>
                <div>
                  <dt>Distance</dt>
                  <dd>{formatDistance(selectedActivity.distance_m)}</dd>
                </div>
                <div>
                  <dt>Moving time</dt>
                  <dd>{formatDuration(selectedActivity.moving_time_s)}</dd>
                </div>
              </dl>
            ) : (
              <p>Select an activity to see metadata.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}

export default App
