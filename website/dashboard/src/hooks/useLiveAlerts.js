import { useEffect, useRef, useState } from 'react';
import { API_BASE } from '../lib/config';
import { normalizeAlert } from '../lib/api';

const LS_KEY = 'seemadrishti.alerts';

function loadCached() {
  try {
    const raw = JSON.parse(localStorage.getItem(LS_KEY));
    return Array.isArray(raw) ? raw : [];
  } catch { return []; }
}
function saveCached(alerts) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(alerts)); } catch { /* ignore */ }
}

// Subscribes to the backend alert WebSocket, merges live alerts into state,
// and reports connection status. Returns { alerts, status, reconcile }.
// Last-known alerts are cached to localStorage so that if the backend is down
// at load time the dashboard still shows stale-but-visible data (never blank).
export function useLiveAlerts({ sector } = {}) {
  const [alerts, setAlerts] = useState(loadCached);
  const [status, setStatus] = useState('connecting');
  const wsRef = useRef(null);
  const alertsRef = useRef([]);

  const push = (items) => {
    // Merge newest-first, dedup by _id so socket confirmations reconcile
    // with anything optimistically applied.
    const map = new Map();
    // Merge oldest-first so that newer items overwrite older ones in the map.
    if (items) [...alertsRef.current, ...items].forEach((a) => map.set(a._id, a));
    else alertsRef.current.forEach((a) => map.set(a._id, a));
    
    alertsRef.current = Array.from(map.values())
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
      .slice(0, 100); // Keep max 100 live alerts in memory
      
    setAlerts(alertsRef.current);
    saveCached(alertsRef.current);
  };

  useEffect(() => {
    let disposed = false;
    let retry = null;

    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const ws = new WebSocket(`${proto}://${window.location.host}${API_BASE}/ws/alerts`);
      wsRef.current = ws;

      ws.onopen = () => { if (!disposed) setStatus('live'); };
      ws.onmessage = (e) => {
        try {
          const raw = JSON.parse(e.data);
          const alert = normalizeAlert(raw);
          push([alert]);
          
          // Play alarm sound on fence breach / intrusion / watchlist / high-severity alerts
          const title = (alert.title || '').toLowerCase();
          const sev = (alert.severity || '').toLowerCase();
          if (title.includes('fence breach') || title.includes('intrusion') ||
              title.includes('watchlist') || alert.watchlistHit ||
              sev === 'high' || sev === 'critical') {
            try {
              const ctx = new (window.AudioContext || window.webkitAudioContext)();
              const osc = ctx.createOscillator();
              const gain = ctx.createGain();
              
              osc.type = 'square';
              osc.frequency.setValueAtTime(600, ctx.currentTime);
              osc.frequency.exponentialRampToValueAtTime(1200, ctx.currentTime + 0.3);
              
              gain.gain.setValueAtTime(0, ctx.currentTime);
              gain.gain.linearRampToValueAtTime(0.3, ctx.currentTime + 0.05);
              gain.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.5);
              
              osc.connect(gain);
              gain.connect(ctx.destination);
              osc.start(ctx.currentTime);
              osc.stop(ctx.currentTime + 0.5);
            } catch(err) { /* ignore audio errors */ }
          }
        } catch { /* ignore malformed frames */ }
      };
      ws.onerror = () => { if (!disposed) setStatus('error'); };
      ws.onclose = () => {
        if (disposed) return;
        setStatus('offline');
        retry = setTimeout(connect, 3000);
      };
    };

    connect();
    return () => {
      disposed = true;
      if (retry) clearTimeout(retry);
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sector]);

  return { alerts, status, push };
}
