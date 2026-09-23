import { useCallback, useEffect, useState } from "react";

/**
 * useZoneStatus.js — single source of truth for the zone radar.
 * State: zone array + selectedId. Zone shape:
 * { id, name, cam_id, status:'green'|'orange'|'red'|'offline', ack:bool,
 *   headcount, behaviour, confidence, detected_at, duration, x, y, eventId }
 * x/y are fixed 280-box radar coords. Acknowledge/Resolve mutate the zone,
 * then best-effort POST /api/events/{id}/transition (same shape as the
 * Event state machine OPEN→ESCALATING→ACKED→RESOLVED); local-only when no
 * backend event is linked yet. WS reducer swaps in live status underneath.
 */

// Scattered fixed positions across the range rings (not evenly spaced).
const SEED = [
  { id: "north-fence", name: "North fence", cam_id: "CAM_01", x: 64, y: 88 },
  { id: "gate-road", name: "Gate road", cam_id: "CAM_02", x: 196, y: 64 },
  { id: "south-road", name: "South road", cam_id: "CAM_03", x: 228, y: 196 },
  { id: "riverine-gap", name: "Riverine gap", cam_id: "CAM_04", x: 84, y: 214 },
];

const LS_KEY = "ibvap_zone_radar_v1";
const WS_URL = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/alerts`;

const toStatus = (s) => {
  const v = String(s || "").toLowerCase();
  if (v === "green" || v === "nominal" || v === "low") return "green";
  if (v === "orange" || v === "activity" || v === "medium" || v === "high") return "orange";
  if (v === "red" || v === "intrusion" || v === "critical" || v === "escalating" || v === "dispatched") return "red";
  if (v === "offline") return "offline";
  return "green";
};

function seedZones() {
  return SEED.map((z) => ({
    ...z, status: "green", ack: false, headcount: null, behaviour: "",
    confidence: null, detected_at: "", duration: "", eventId: null,
  }));
}

function loadLS() {
  try {
    const raw = JSON.parse(localStorage.getItem(LS_KEY) || "null");
    if (Array.isArray(raw) && raw.length) return raw;
  } catch { /* ignore */ }
  return seedZones();
}

async function postTransition(eventId, to_state, actor = "operator") {
  const res = await fetch(`/api/events/${eventId}/transition`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ to_state, actor }),
  });
  if (!res.ok) throw new Error(`transition failed → ${res.status}`);
  return res.json();
}

export default function useZoneStatus() {
  const [zones, setZones] = useState(loadLS);
  const [selectedId, setSelectedId] = useState(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    try { localStorage.setItem(LS_KEY, JSON.stringify(zones)); } catch { /* ignore */ }
  }, [zones]);

  // Static layout from backend; keep local x/y + ack, take live status fields.
  useEffect(() => {
    let stop = false;
    fetch("/api/zones")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (stop || !d || !Array.isArray(d.zones) || !d.zones.length) return;
        setZones((prev) => {
          const pos = new Map(prev.map((z) => [z.cam_id, z]));
          const seedPos = SEED;
          return d.zones.slice(0, 8).map((z, i) => {
            const camId = z.camera_id || `CAM_${String(i + 1).padStart(2, "0")}`;
            const keep = pos.get(camId);
            const fallback = seedPos[i % seedPos.length];
            return {
              id: z.zone_id || camId.toLowerCase(),
              name: z.name || camId,
              cam_id: camId,
              x: keep?.x ?? fallback.x,
              y: keep?.y ?? fallback.y,
              status: z.status === "offline" ? "offline" : toStatus(z.status),
              ack: keep?.ack ?? false,
              headcount: keep?.headcount ?? null,
              behaviour: keep?.behaviour ?? "",
              confidence: keep?.confidence ?? null,
              detected_at: keep?.detected_at ?? "",
              duration: keep?.duration ?? "",
              eventId: keep?.eventId ?? null,
            };
          });
        });
      })
      .catch(() => {});
    return () => { stop = true; };
  }, []);

  // Live reducer: WS alert/event → zone status + metadata.
  useEffect(() => {
    let ws; let retry; let alive = true;
    const connect = () => {
      try { ws = new WebSocket(WS_URL); } catch { schedule(); return; }
      ws.onopen = () => setConnected(true);
      ws.onclose = () => { setConnected(false); schedule(); };
      ws.onerror = () => { try { ws.close(); } catch { /* ignore */ } };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          const cams = msg.cameras || (msg.camera_id ? [msg.camera_id] : []);
          if (!cams.length) return;
          const level = toStatus(msg.state || msg.danger_label || msg.severity);
          if (level === "green") return; // radar only escalates; resolve is manual
          const ts = msg.timestamp || new Date().toISOString();
          setZones((prev) => prev.map((z) => {
            if (!cams.includes(z.cam_id)) return z;
            const beh = msg.activities?.[0] || msg.event_type || z.behaviour;
            return {
              ...z,
              status: level === "red" ? "red" : "orange",
              ack: false,
              headcount: msg.headcount ?? msg.humans_detected ?? z.headcount,
              behaviour: typeof beh === "string" ? beh : z.behaviour,
              confidence: msg.confidence ?? z.confidence,
              detected_at: z.detected_at || ts,
              eventId: msg.event_id || msg.incident_id || z.eventId,
            };
          }));
        } catch { /* ignore */ }
      };
    };
    const schedule = () => { if (alive) retry = setTimeout(connect, 3000); };
    connect();
    return () => { alive = false; clearTimeout(retry); try { ws && ws.close(); } catch { /* ignore */ } };
  }, []);

  const selectZone = useCallback((id) => setSelectedId(id), []);

  const acknowledge = useCallback((id) => {
    setZones((prev) => {
      const z = prev.find((zz) => zz.id === id);
      if (z?.eventId) postTransition(z.eventId, "ACKED").catch(() => {});
      return prev.map((zz) => (zz.id === id ? { ...zz, ack: true } : zz));
    });
  }, []);

  const resolve = useCallback((id) => {
    setZones((prev) => {
      const z = prev.find((zz) => zz.id === id);
      if (z?.eventId) postTransition(z.eventId, "RESOLVED").catch(() => {});
      return prev.map((zz) =>
        (zz.id === id
          ? { ...zz, status: "green", ack: true, headcount: null, behaviour: "",
              confidence: null, detected_at: "", duration: "", eventId: null }
          : zz));
    });
    setSelectedId((cur) => cur); // keep selection; detail re-renders green state
  }, []);

  return { zones, selectedId, selectZone, acknowledge, resolve, connected };
}
