/**
 * ZoneRadarPanel — grouped intrusion radar, sci-fi edition.
 */
import ZoneNode from "./ZoneNode";
import ZoneDetail from "./ZoneDetail";
import useZoneStatus from "../../hooks/useZoneStatus";

const LEGEND = [
  { label: "Nominal", color: "#39ff88" },
  { label: "Activity", color: "#ff6b2c" },
  { label: "Intrusion", color: "#ff2d55" },
  { label: "Offline", color: "#5f7a95" },
];

export default function ZoneRadarPanel() {
  const { zones, selectedId, selectZone, acknowledge, resolve } = useZoneStatus();
  const selected = zones.find((z) => z.id === selectedId) || null;
  return (
    <div className="hud-panel p-4">
      <div className="mono mb-3 flex items-center justify-between text-[10px] uppercase tracking-[0.24em]">
        <span className="hud-title">Zone Radar</span>
        <span className="text-[#5f7a95]">{zones.length} ZONES</span>
      </div>
      <div className="flex flex-wrap gap-4">
        <div className="shrink-0">
          <div className="relative" style={{ width: 280, height: 280 }}>
            <div className="absolute inset-0 rounded-full" style={{ background: 'radial-gradient(circle at center, rgba(0,240,255,0.1), transparent 65%)' }} />
            <svg viewBox="0 0 280 280" width={280} height={280} className="absolute inset-0">
              {[44, 87, 130].map((r) => (
                <circle key={r} cx={140} cy={140} r={r} fill="none" stroke="rgba(0,240,255,0.22)" strokeWidth={1} />
              ))}
              <circle cx={140} cy={140} r={130} fill="none" stroke="rgba(0,240,255,0.5)" strokeWidth={1.2} style={{ filter: 'drop-shadow(0 0 8px rgba(0,240,255,0.5))' }} />
              <line x1={140} y1={10} x2={140} y2={270} stroke="rgba(0,240,255,0.18)" strokeWidth={1} />
              <line x1={10} y1={140} x2={270} y2={140} stroke="rgba(0,240,255,0.18)" strokeWidth={1} />
            </svg>
            <div
              aria-hidden
              className="animate-radar-sweep pointer-events-none absolute inset-0 rounded-full"
              style={{
                transformOrigin: "140px 140px",
                background: "conic-gradient(from 0deg at 140px 140px, rgba(0,240,255,0.55) 0deg, rgba(0,240,255,0.12) 24deg, transparent 60deg)",
                filter: 'drop-shadow(0 0 12px rgba(0,240,255,0.4))',
              }}
            />
            <div className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#00f0ff] shadow-[0_0_12px_4px_rgba(0,240,255,0.7)]" />
            <div className="absolute inset-0">
              {zones.map((z) => (
                <ZoneNode key={z.id} zone={z} selected={z.id === selectedId} onSelect={selectZone} />
              ))}
            </div>
          </div>
          <div className="mt-2 flex items-center justify-center gap-3">
            {LEGEND.map((l) => (
              <span key={l.label} className="flex items-center gap-1.5 mono text-[9px] uppercase tracking-[0.15em] text-[#5f7a95]">
                <span className="inline-block h-2 w-2 rounded-full" style={{ background: l.color, boxShadow: `0 0 6px 1px ${l.color}` }} />
                {l.label}
              </span>
            ))}
          </div>
        </div>
        <div className="min-w-[240px] flex-1">
          <ZoneDetail zone={selected} onAcknowledge={acknowledge} onResolve={resolve} />
        </div>
      </div>
    </div>
  );
}
