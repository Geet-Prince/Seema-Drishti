/**
 * ZoneDetail — right detail panel for the selected radar zone (sci-fi edition).
 */
const BADGE = {
  green: { color: "#39ff88", border: "rgba(57,255,136,0.4)", bg: "rgba(57,255,136,0.1)" },
  orange: { color: "#ff6b2c", border: "rgba(255,107,44,0.45)", bg: "rgba(255,107,44,0.1)" },
  red: { color: "#ff2d55", border: "rgba(255,45,85,0.5)", bg: "rgba(255,45,85,0.12)" },
  offline: { color: "#5f7a95", border: "rgba(95,122,149,0.4)", bg: "rgba(95,122,149,0.1)" },
};

const LABEL = { green: "Nominal", orange: "Activity", red: "Intrusion", offline: "Offline" };

function Row({ k, v }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="mono text-[10px] uppercase tracking-[0.18em] text-[#5f7a95]">{k}</span>
      <span className="mono text-[12px] text-white">{v}</span>
    </div>
  );
}

export default function ZoneDetail({ zone, onAcknowledge, onResolve }) {
  if (!zone) {
    return (
      <div className="flex h-full min-h-[220px] flex-col items-center justify-center gap-2">
        <span className="mono text-[10px] uppercase tracking-[0.25em] text-[#5f7a95]">// Select zone node</span>
        <span className="mono text-[9px] tracking-[0.15em] text-[#5f7a95]/60">on radar to inspect feed</span>
      </div>
    );
  }
  const b = BADGE[zone.status] || BADGE.green;
  const alerted = zone.status === "orange" || zone.status === "red";
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-display text-[14px] font-bold tracking-[0.08em] text-white">{zone.name}</div>
          <div className="mono mt-0.5 text-[10px] tracking-[0.2em] text-[#00f0ff]/70">{zone.cam_id}</div>
        </div>
        <span className="mono rounded-sm px-2 py-1 text-[9px] font-bold uppercase tracking-[0.18em]"
          style={{ color: b.color, border: `1px solid ${b.border}`, background: b.bg, textShadow: `0 0 8px ${b.color}` }}>
          {LABEL[zone.status] || zone.status}{zone.ack ? " · ACK" : ""}
        </span>
      </div>

      <div className="flex h-32 items-center justify-center rounded-sm border border-[rgba(0,240,255,0.15)] bg-black/50">
        {zone.status === "offline" ? (
          <span className="mono text-[10px] uppercase tracking-[0.25em] text-[#5f7a95]">// No signal</span>
        ) : (
          <span className="flex items-center gap-2 mono text-[10px] uppercase tracking-[0.2em] text-[#9db4cc]">
            <span className="inline-block h-2 w-2 animate-blink-dot rounded-full bg-[#ff2d55] shadow-[0_0_8px_2px_rgba(255,45,85,0.7)]" />
            Live · {zone.cam_id}
          </span>
        )}
      </div>

      {alerted && (
        <>
          <div className="divide-y divide-[rgba(0,240,255,0.1)] rounded-sm border border-[rgba(0,240,255,0.15)] bg-black/30 px-3">
            <Row k="Headcount" v={zone.headcount ?? "—"} />
            <Row k="Behaviour" v={zone.behaviour || "—"} />
            <Row k="Confidence" v={zone.confidence != null ? `${zone.confidence}%` : "—"} />
            <Row k="Detected" v={[zone.detected_at, zone.duration].filter(Boolean).join(" · ") || "—"} />
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={() => onAcknowledge?.(zone.id)} disabled={zone.ack}
              className="flex-1 rounded-sm border border-[rgba(255,176,32,0.45)] bg-[rgba(255,176,32,0.1)] px-3 py-2 mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#ffb020] transition-all hover:bg-[rgba(255,176,32,0.22)] disabled:opacity-40">
              {zone.ack ? "Acked" : "Acknowledge"}
            </button>
            <button type="button" onClick={() => onResolve?.(zone.id)}
              className="flex-1 rounded-sm border border-[rgba(57,255,136,0.45)] bg-[rgba(57,255,136,0.1)] px-3 py-2 mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#39ff88] transition-all hover:bg-[rgba(57,255,136,0.22)]">
              Resolve
            </button>
          </div>
        </>
      )}
    </div>
  );
}
