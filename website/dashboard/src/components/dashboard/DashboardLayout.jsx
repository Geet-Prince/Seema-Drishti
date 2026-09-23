import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, radarPoint } from '../../lib/api';
import { liveStreamUrl, cameraStreamUrl } from '../../lib/config';
import { useLiveAlerts } from '../../hooks/useLiveAlerts';
import TopBar from './TopBar';
import StatStrip from './StatStrip';
import CameraPanel from './CameraPanel';
import MonitorPanel from './MonitorPanel';
import DetailPanel from './DetailPanel';
import ZoneRadarPanel from './ZoneRadarPanel';
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
  const [liveHuman, setLiveHuman] = useState(null);

  const refreshAll = useCallback(() => {
    api.events().then((rows) => push(rows)).catch(() => {});
    api.incidents().then((rows) => { setIncidents(rows); saveLS('seemadrishti.incidents', rows); }).catch(() => {});
    api.stats().then((rows) => { setStats(rows); saveLS('seemadrishti.stats', rows); }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  useEffect(() => {
    setFeedOnline(connStatus !== 'offline');
  }, [connStatus]);

  const prevConn = useRef(connStatus);
  useEffect(() => {
    const prev = prevConn.current;
    prevConn.current = connStatus;
    if (connStatus === 'live' && (prev === 'offline' || prev === 'error' || prev === 'connecting')) {
      refreshAll();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connStatus]);

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

  const detections = useMemo(
    () =>
      alerts
        .filter((a) => Array.isArray(a.bbox) && a.bbox.length === 4)
        .slice(0, 6)
        .map((a) => {
          const [x1, y1, x2, y2] = a.bbox;
          return {
            x: x1, y: y1, w: x2 - x1, h: y2 - y1,
            label: a.dangerLabel || a.title, confidence: a.confidence != null ? a.confidence / 100 : undefined,
            severity: a.severity,
          };
        }),
    [alerts],
  );

  const humans = liveHuman;
  const radarPoints = useMemo(() => alerts.slice(0, 14).map(radarPoint), [alerts]);

  const selectedItem = useMemo(() => {
    if (!selectedId) return null;
    return alerts.find((a) => a._id === selectedId) || incidents.find((i) => i._id === selectedId) || null;
  }, [selectedId, alerts, incidents]);

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
    api.updateStatus(item, status)
      .then(() => {
        api.stats().then((rows) => { setStats(rows); saveLS('seemadrishti.stats', rows); }).catch(() => {});
      })
      .catch(() => {});
  }

  const critCount = alerts.filter((a) => a.severity === 'critical').length;

  return (
    <div className="relative flex min-h-screen flex-col bg-void text-fg">
      {/* ——— ambient sci-fi backdrop ——— */}
      <div className="pointer-events-none fixed inset-0 z-0">
        <div
          className="absolute inset-0 animate-grid-drift opacity-[0.55]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(0,240,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(0,240,255,0.05) 1px, transparent 1px)',
            backgroundSize: '44px 44px',
            maskImage: 'radial-gradient(ellipse 90% 70% at 50% 0%, black 30%, transparent 75%)',
          }}
        />
        <div className="absolute -top-40 left-1/4 h-[420px] w-[560px] rounded-full bg-[rgba(0,240,255,0.07)] blur-[130px]" />
        <div className="absolute -top-24 right-1/5 h-[300px] w-[420px] rounded-full bg-[rgba(139,92,246,0.09)] blur-[120px]" />
        <div className="absolute bottom-0 left-0 h-[280px] w-[480px] rounded-full bg-[rgba(0,240,255,0.04)] blur-[120px]" />
        <div className="absolute inset-0" style={{ background: 'radial-gradient(ellipse 120% 90% at 50% 110%, transparent 55%, rgba(0,0,0,0.55) 100%)' }} />
      </div>

      {showPersonnelModal && <PersonnelManager onClose={() => setShowPersonnelModal(false)} />}

      <div className="relative z-10">
        <TopBar
          sector={sector}
          onSectorChange={setSector}
          connectionStatus={connStatus}
          onPersonnelClick={() => setShowPersonnelModal(true)}
        />
      </div>

      {/* connection beam */}
      {connStatus !== 'live' && (
        <div className="relative z-10 overflow-hidden border-b border-[rgba(255,45,85,0.3)] bg-[rgba(255,45,85,0.07)]">
          <div className="absolute inset-y-0 w-1/3 animate-beam bg-gradient-to-r from-transparent via-[rgba(255,45,85,0.25)] to-transparent" />
          <div className="flex items-center justify-center gap-2 px-4 py-1.5">
            <span className={`h-1.5 w-1.5 rounded-full ${connStatus === 'connecting' ? 'animate-pulse bg-[#ffb020]' : 'bg-[#ff2d55] animate-blink-dot'}`} />
            <span className="mono text-[10px] tracking-[0.24em] uppercase text-[#9db4cc]">
              {connStatus === 'connecting' ? '// Re-establishing secure uplink…' : '// Uplink down — tactical cache engaged · showing last known data'}
            </span>
          </div>
        </div>
      )}

      {/* critical alert ticker */}
      {critCount > 0 && connStatus === 'live' && (
        <div className="relative z-10 overflow-hidden border-b border-[rgba(255,45,85,0.35)] bg-[rgba(255,45,85,0.09)]">
          <div className="flex items-center gap-3 px-4 py-1.5">
            <span className="flex items-center gap-1.5 rounded-sm bg-[#ff2d55] px-2 py-0.5 mono text-[9px] font-bold tracking-[0.2em] text-white animate-blink-dot">
              ▲ THREAT
            </span>
            <span className="mono text-[10px] tracking-[0.2em] uppercase text-[#ff8fa3]">
              {critCount} critical contact{critCount === 1 ? '' : 's'} on scope — immediate review advised
            </span>
          </div>
        </div>
      )}

      <main className="relative z-10 mx-auto flex w-full max-w-[1760px] flex-1 flex-col gap-4 p-4">
        <StatStrip stats={statsLoading && stats.length === 0 ? [] : stats} />

        <div className="grid grid-cols-1 gap-4 min-[1100px]:grid-cols-[360px_minmax(0,1fr)_360px] min-[1100px]:items-start">
          <div className="flex min-[1100px]:order-1 max-[1099px]:order-3 flex-col gap-4">
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
            <ZoneRadarPanel />
          </div>

          <div className="min-w-0 min-[1100px]:order-2 max-[1099px]:order-1">
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

          <div className="min-[1100px]:order-3 max-[1099px]:order-2">
            <div className="hud-panel md:sticky md:top-4">
              <div className="flex items-center justify-between border-b border-[rgba(0,240,255,0.14)] px-3 py-2.5">
                <span className="hud-title">◈ Target Dossier</span>
                <span className="mono text-[9px] tracking-[0.2em] text-[#5f7a95]">
                  {selectedItem ? 'LOCKED' : 'STANDBY'}
                </span>
              </div>
              <div className="max-h-[calc(100vh-220px)] overflow-y-auto p-3">
                <DetailPanel item={selectedItem} onStatusChange={updateStatus} />
              </div>
            </div>
          </div>
        </div>

        <footer className="flex items-center justify-between px-1 pb-1 pt-2">
          <span className="mono text-[9px] tracking-[0.28em] uppercase text-[#5f7a95]/70">
            SEEMA DRISHTI ◈ EDGE-NATIVE ◈ ZERO-CLOUD ◈ AES-256
          </span>
          <span className="mono text-[9px] tracking-[0.28em] uppercase text-[#5f7a95]/70">
            SIH 2026 · SSB BORDER GRID
          </span>
        </footer>
      </main>
    </div>
  );
}
