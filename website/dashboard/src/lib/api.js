import { API_BASE, snapshotUrl, hashish } from './config';

// Convert SOME_ENUM_VALUE or some_enum_value to Some Enum Value.
export function formatTitle(raw) {
  if (!raw) return '';
  return String(raw)
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

// Normalize a backend event/alert payload into the app's alert item contract.
// Handles BOTH the live WebSocket alert shape and the persisted SQLite events
// rows returned by GET /api/events (different field names).
export function normalizeAlert(raw) {
  const sevCode = severityFromLabel(raw.danger_label, raw.severity, raw.danger_score);
  const incidentId = raw.incident_id || raw.event_id;
  const timestamp = raw.timestamp || raw.created_at || new Date().toISOString();
  const snapshot = raw.snapshot || raw.snapshot_path || '';
  const ubbox =
    (Array.isArray(raw.bbox) && raw.bbox.length === 4 && raw.bbox.map(Number)) ||
    parseAttrs(raw.attributes, 'bbox');
  // Identity rides inside attributes (set by the pipeline's face worker).
  // normalizeAlert used to drop `attributes`, so every row rendered Unknown.
  const attrs = parseAttrs(raw.attributes, null) || (typeof raw.attributes === 'object' ? raw.attributes : null) || {};
  const identity = attrs.identity || raw.identity || 'Unknown';
  const badgeNumber = attrs.badge_number || raw.badge_number || '';
  const faceImage = attrs.image_path || raw.image_path || '';
  const watchlistHit = Boolean(attrs.watchlist_match ?? raw.watchlist_hit ?? raw.watchlist_match ?? false);

  return {
    _id: incidentId,
    kind: 'alert',
    severity: sevCode,
    dangerLabel: raw.danger_label || sevCode.toUpperCase(),
    dangerScore: Number(raw.danger_score || 0),
    title: formatTitle(raw.event_type || raw.module || 'Alert'),
    module: raw.module || '',
    location: `${raw.camera_id || 'CAM_LIVE'}${raw.zone_breaches?.length ? ' · ' + raw.zone_breaches.join(', ') : ''}`,
    sector: 'sector-a',
    cameraId: raw.camera_id || 'CAM_LIVE',
    cameraName: raw.camera_id || 'CAM_LIVE',
    camera: { id: raw.camera_id || 'CAM_LIVE', name: raw.camera_id || 'CAM_LIVE' },
    timestamp,
    status: raw.status || 'new',
    confidence: raw.confidence != null ? Math.round(raw.confidence * 100) : confFromAttrs(raw.attributes),
    trackId: raw.track_id || raw.trackId,
    bbox: ubbox,
    attributes: raw.attributes ?? null,
    identity,
    badgeNumber,
    faceImage,
    watchlistHit,
    snapshotUrl: snapshotUrl(raw.camera_id || 'CAM_LIVE', incidentId, snapshot),
    humansDetected: Number(raw.humans_detected || parseAttrsNum(raw.attributes, 'humans_detected') || 0),
    zoneBreaches: raw.zone_breaches || [],
    activities: raw.activities || [],
    plateNo: raw.plate_no || parseAttrs(raw.attributes, 'plate_no') || '',
    _raw: raw,
  };
}

function parseAttrs(attributes, key) {
  if (typeof attributes !== 'string') return key ? attributes?.[key] : attributes;
  try {
    const o = JSON.parse(attributes);
    return key ? o?.[key] : o;
  } catch {
    return key ? undefined : null;
  }
}

function parseAttrsNum(attributes, key) {
  const v = parseAttrs(attributes, key);
  return typeof v === 'number' ? v : 0;
}

function confFromAttrs(attributes) {
  const c = parseAttrs(attributes, 'confidence');
  return typeof c === 'number' ? Math.round(c * 100) : null;
}

// Normalize a backend incident (persisted folder metadata) into a list item.
export function normalizeIncident(raw) {
  const sevCode = severityFromLabel(raw.danger_label, null);
  const driverFiles = (raw.driver_snapshots || []).filter(Boolean);
  const allSnaps = (raw.snapshots || []).map((f) => snapshotUrl(raw.camera_id || 'CAM_LIVE', raw.incident_id, f));
  const driverUrls = driverFiles.map((f) => snapshotUrl(raw.camera_id || 'CAM_LIVE', raw.incident_id, f));
  const watchlistHits = raw.watchlist_hits || [];
  return {
    _id: raw.incident_id,
    kind: 'incident',
    severity: watchlistHits.length ? 'critical' : sevCode,
    dangerLabel: raw.danger_label || sevCode,
    dangerScore: Number(raw.danger_score || 0),
    title: formatTitle([raw.modules_triggered?.join(', '), 'Incident'].filter(Boolean).join(' — ') || 'Incident'),
    module: raw.modules_triggered?.join(', ') || '',
    location: raw.camera_id || 'CAM_LIVE',
    sector: 'sector-a',
    cameraId: raw.camera_id || 'CAM_LIVE',
    cameraName: raw.camera_id || 'CAM_LIVE',
    camera: { id: raw.camera_id || 'CAM_LIVE', name: raw.camera_id || 'CAM_LIVE' },
    timestamp: raw.last_updated || raw.started_at || new Date().toISOString(),
    startedAt: raw.started_at,
    status: raw.status || 'open',
    confidence: raw.confidence != null ? Math.round(raw.confidence * 100) : null,
    trackId: raw.track_ids?.[0],
    snapshotUrl: snapshotUrl(raw.camera_id || 'CAM_LIVE', raw.incident_id, raw.snapshots?.[0]),
    humansDetected: raw.humans_detected || 0,
    vehiclesDetected: raw.vehicles_detected || 0,
    weaponsDetected: raw.weapons_detected || 0,
    facesCaptured: raw.faces_captured || 0,
    snapshotCount: raw.snapshot_count || (raw.snapshots?.length) || 0,
    snapshots: allSnaps,
    driverSnapshots: driverUrls,
    watchlistHits,
    watchlistHit: watchlistHits.length > 0,
    zoneBreaches: raw.zone_breaches || [],
    activities: raw.activities_detected || [],
    modules: raw.modules_triggered || [],
    plateNumbers: raw.plate_numbers || [],
    vehicleTypes: raw.vehicle_types || [],
    _raw: raw,
  };
}

function severityFromLabel(dangerLabel, severity, score) {
  const s = String(dangerLabel || '').toUpperCase();
  const v = String(severity || '').toLowerCase();
  if (s.includes('CRIT') || s.includes('CRITICAL') || v === 'critical') return 'critical';
  if (s.includes('HIGH') || v === 'high') return 'high';
  if (s.includes('MED') || v === 'medium') return 'medium';
  if (s === 'LOW' || v === 'low') return 'low';
  if (score != null && score >= 80) return 'critical';
  if (score != null && score >= 60) return 'high';
  if (score != null && score >= 40) return 'medium';
  if (score != null && score >= 20) return 'low';
  return 'informational';
}

// Compute a stable schematic "radar" dot position from an id + score.
// Radius is clamped so every point lands inside the 0..100% container; the
// container is overflow-hidden, so anything with radius > 50 (r>50 pips past
// center: 50+r > 100) would be clipped out of view.
export function radarPoint(item) {
  const seed = hashish(item._id || '');
  const r = 6 + (seed % 42); // radius ring kept within bounds (6..48)
  const a = (seed % 1000) / 1000 * Math.PI * 2;
  return {
    id: item._id,
    x: 50 + r * Math.cos(a),
    y: 50 + r * Math.sin(a),
    severity: item.severity || 'informational',
    label: item.title,
    item,
  };
}

async function getJson(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`Request failed: ${path} → ${res.status}`);
  return res.json();
}

export const api = {
  async events(limit = 80) {
    const rows = await getJson(`/api/events?limit=${limit}`);
    return (rows || []).map(normalizeAlert);
  },
  async incidents(limit = 80) {
    const rows = await getJson(`/api/incidents?limit=${limit}`);
    return (rows || []).map(normalizeIncident);
  },
  async incident(id) {
    return getJson(`/api/incidents/${id}`);
  },
  async watchlist() {
    const res = await getJson('/api/watchlist');
    return res.data || [];
  },
  // Per-frame live telemetry from the camera pipeline (same source as the feed).
  // Returns { humans, frame_id, updated_at, live }. "live" is false when the
  // pipeline hasn't written recently — callers should render an unknown state
  // (--), never a silent 0.
  async live() {
    return getJson('/api/live');
  },
  async updateStatus(item, status) {
    const endpoint = item.kind === 'incident' ? `/api/incidents/${item._id}` : `/api/alerts/${item._id}`;
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    if (!res.ok) throw new Error(`Status update failed → ${res.status}`);
    return res.json();
  },
  async stats() {    const s = await getJson('/api/stats');
    const card = (key, severity, overrideLabel) => ({
      key,
      label: overrideLabel || (s[key] && s[key].label) || key.charAt(0).toUpperCase() + key.slice(1),
      value: (s[key] && s[key].value) || 0,
      trend: (s[key] && s[key].trend) || 0,
      direction: (s[key] && s[key].direction) || 'flat',
      tone: (s[key] && s[key].tone) || 'neutral',
      severity,
      sparkline: (s[key] && s[key].sparkline) || [],
    });
    return [
      card('events', 'nominal'),
      card('humans', 'nominal'),
      card('vehicles', 'nominal'),
      card('medium', 'medium'),
      card('high', 'high'),
      card('critical', 'critical'),
      card('incidents', 'nominal'),
    ];
  },
};
