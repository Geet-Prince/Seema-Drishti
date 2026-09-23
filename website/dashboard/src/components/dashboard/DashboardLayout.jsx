import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, radarPoint } from '../../lib/api';
import { liveStreamUrl, cameraStreamUrl } from '../../lib/config';
import { useLiveAlerts } from '../../hooks/useLiveAlerts';
import TopBar from './TopBar';
import StatStrip from './StatStrip';
import CameraPanel from './CameraPanel';
import MonitorPanel from './MonitorPanel';
import DetailPanel from './DetailPanel';
import PersonnelManager from './PersonnelManager';

function loadLS(key, fallback) {
  try {
    const raw = JSON.parse(localStorage.getItem(key));
    return raw ?? fallback;
  } catch { return fallback; }
}
function saveLS(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
}

export default function DashboardLayout() {
  const { alerts, status: connStatus, push } = useLiveAlerts();
  
  const [showPersonnelModal, setShowPersonnelModal] = useState(false);

  const [incidents, setIncidents] = useState(() => loadLS('seemadrishti.incidents', []));
  const [stats, setStats] = useState(() => loadLS('seemadrishti.stats', []));
  const [statsLoading, setStatsLoading] = useState(true);
  const [incLoading, setIncLoading] = useState(true);
  const [sector, setSector] = useState('sector-a');
  const [selectedId, setSelectedId] = useState(null);
  const [feedOnline, setFeedOnline] = useState(true);
  // Per-frame live human count from the pipeline. null = source unknown/stale,
  // so the HUD renders "--" instead of a silent 0.
  const [liveHuman, setLiveHuman] = useState(null);

  // Refetch the initial-load REST data (events, incidents, stats) so we catch
  // up on anything missed. Runs on mount AND whenever the socket reconnects â€”
  // we never assume the socket replays everything lost while offline. Results
  // are also cached to localStorage so a page load during a backend outage
  // still shows the last known data instead of a blank dashboard.
  const refreshAll = useCallback(() => {
    api.events().then((rows) => push(rows)).catch(() => {});
    api.incidents().then((rows) => { setIncidents(rows); saveLS('seemadrishti.incidents', rows); }).catch(() => {});
    api.stats().then((rows) => { setStats(rows); saveLS('seemadrishti.stats', rows); }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Initial load (then clear the loading flags either way).
  // Periodic refresh for stats and incidents (every 5s)
  useEffect(() => {
    const t = setInterval(() => {
      api.incidents().then((rows) => { setIncidents(rows); saveLS('seemadrishti.incidents', rows); }).catch(() => {});
      api.stats().then((rows) => { setStats(rows); saveLS('seemadrishti.stats', rows); }).catch(() => {});
    }, 5000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      await Promise.allSettled([
        api.events().then((rows) => { if (!cancelled) push(rows); }),
        api.incidents().then((rows) => { if (!cancelled) { setIncidents(rows); saveLS('seemadrishti.incidents', rows); } }),
        api.stats().then((rows) => { if (!cancelled) { setStats(rows); saveLS('seemadrishti.stats', rows); } }),
      ]);
      if (!cancelled) { setStatsLoading(false); setIncLoading(false); }
    };
    load();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Track socket status â†’ feed health.
  useEffect(() => {
    setFeedOnline(connStatus !== 'offline');
  }, [connStatus]);

  // When the socket returns to 'live' after being down, resync from REST so we
  // don't rely on the socket replaying everything missed while offline.
  const prevConn = useRef(connStatus);
  useEffect(() => {
    const prev = prevConn.current;
    prevConn.current = connStatus;
    if (connStatus === 'live' && (prev === 'offline' || prev === 'error' || prev === 'connecting')) {
      refreshAll();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connStatus]);

  // Poll the per-frame live human count. Uses `live:false` (rather than the
  // value) to decide freshness; on failure we surface it as "--", not 0.
  useEffect(() => {
    let cancelled = false;
    let timer = null;
    const poll = () => {
      api.live()
        .then((info) => { if (!cancelled) setLiveHuman(info && info.live ? info.humans : null); })
        .catch(() => { if (!cancelled) setLiveHuman(null); });
      timer = setTimeout(poll, 1500);
    };
    poll();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, []);

  // Fetch real camera list from the backend.
  const [cameras, setCameras] = useState([]);
  const [activeCamId, setActiveCamId] = useState('__grid__');
  useEffect(() => {
    const poll = () => {
      fetch(`/api/cameras`)
        .then((r) => r.json())
        .then((list) => { if (Array.isArray(list)) setCameras(list); })
        .catch(() => {});
    };
    poll();
    const t = setInterval(poll, 5000);
    return () => clearInterval(t);
  }, []);

  const activeCamera = activeCamId === '__grid__'
    ? { id: '__grid__', name: 'All Cameras' }
    : cameras.find((c) => c.id === activeCamId) || { id: '__grid__', name: 'All Cameras' };

  const activeStreamSrc = activeCamId === '__grid__'
    ? liveStreamUrl()
    : cameraStreamUrl(activeCamId);

  // Detection boxes for the feed overlay â€” recent alerts that carry a bbox.
  const detections = useMemo(
    () =>
      alerts
        .filter((a) => Array.isArray(a.bbox) && a.bbox.length === 4)
        .slice(0, 6)
        .map((a) => {
          const [x1, y1, x2, y2] = a.bbox;
          const known = a.identity && a.identity !== 'Unknown' ? ` · ${a.identity}` : '';
          return {
            x: x1, y: y1, w: x2 - x1, h: y2 - y1,
            label: `${a.dangerLabel || a.title}${known}`, confidence: a.confidence != null ? a.confidence / 100 : undefined,
            severity: a.severity,
          };
        }),
    [alerts],
  );

  // Human count shown on the feed HUD â€” reads the pipeline's per-frame live
  // count (same source as the feed), NOT the historical alert aggregate that
  // backs the "Humans" stat card. null â†’ live source unknown, show "--".
  const humans = liveHuman;

  // Radar blips derived from recent alerts (schematic positions).
  const radarPoints = useMemo(() => alerts.slice(0, 14).map(radarPoint), [alerts]);

  const selectedItem = useMemo(() => {
    if (!selectedId) return null;
    return alerts.find((a) => a._id === selectedId) || incidents.find((i) => i._id === selectedId) || null;
  }, [selectedId, alerts, incidents]);

  // Optimistic status update; best-effort PATCH, reconciled by socket pushes.
  function updateStatus(item, status) {
    if (item.kind === 'incident') {
      const next = incidents.map((it) => (it._id === item._id ? { ...it, status } : it));
      setIncidents(next);
      saveLS('seemadrishti.incidents', next);
    } else {
      const updated = alerts.map((it) => (it._id === item._id ? { ...it, status } : it));
      push(updated);
    }
    setSelectedId(item._id);

    // Persist to the real endpoint; on success re-fetch stats so any
    // backend-derived counts update without a full page refresh.
    api.updateStatus(item, status)
      .then(() => {
        api.stats().then((rows) => { setStats(rows); saveLS('seemadrishti.stats', rows); }).catch(() => {});
      })
      .catch(() => {});
  }

  return (
    <div className="flex min-h-screen flex-col bg-ink">
      {showPersonnelModal && <PersonnelManager onClose={() => setShowPersonnelModal(false)} />}
      
      {connStatus !== 'live' && (
        <div className={`h-0.5 shrink-0 ${connStatus === 'connecting' ? 'bg-ghost' : 'bg-sev-critical'}`} />
      )}
      <TopBar 
        sector={sector} 
        onSectorChange={setSector} 
        connectionStatus={connStatus} 
        onPersonnelClick={() => setShowPersonnelModal(true)} 
      />

      {connStatus !== 'live' && (
        <div className={`flex items-center justify-center gap-2 border-b px-4 py-1.5 ${
          connStatus === 'connecting'
            ? 'border-hairline bg-ghost/10'
            : 'border-sev-critical/30 bg-sev-critical/10'
        }`}>
          <span className={`h-1.5 w-1.5 rounded-full ${connStatus === 'connecting' ? 'animate-pulse bg-ghost' : 'bg-sev-critical'}`} />
          <span className="mono text-[10px] tracking-[0.08em] uppercase text-ghost">
            {connStatus === 'connecting'
              ? 'Reconnectingâ€¦'
              : 'Offline â€” showing last known data'}
          </span>
        </div>
      )}

      <main className="mx-auto flex w-full max-w-[1680px] flex-1 flex-col gap-4 p-4">
        <StatStrip stats={statsLoading && stats.length === 0 ? [] : stats} />

        <div className="grid grid-cols-1 gap-4 min-[900px]:grid-cols-[340px_minmax(0,1fr)_340px] min-[900px]:items-start">
          <div className="min-[900px]:order-1 max-[899px]:order-3">
            <CameraPanel
              activeCamera={activeCamera}
              cameras={cameras}
              detections={detections}
              onSelectCamera={(id) => { 
                setActiveCamId(id); 
                setSelectedId(null);
                if (id !== '__grid__') {
                  fetch(`/api/cameras/${id}/select`, { method: 'POST' }).catch(() => {});
                }
              }}
              feedOnline={feedOnline}
              humans={humans}
              streamSrc={activeStreamSrc}
            />
          </div>

          <div className="min-w-0 min-[900px]:order-2 max-[899px]:order-1">
            <MonitorPanel
              alerts={alerts}
              incidents={incidents}
              points={radarPoints}
              alertsLoading={false}
              incidentsLoading={incLoading}
              selectedId={selectedId}
              onSelect={setSelectedId}
              streamSrc={activeCamId !== '__grid__' ? activeStreamSrc : null}
            />
          </div>

          <div className="min-[900px]:order-3 max-[899px]:order-2">
            <div className="rounded-lg border border-hairline bg-panel/40 md:sticky md:top-4">
              <div className="mono border-b border-hairline px-3 py-2 text-[10px] tracking-[0.2em] uppercase text-ghost">
                Detail View
              </div>
              <div className="p-3">
                <DetailPanel item={selectedItem} onStatusChange={updateStatus} />
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

