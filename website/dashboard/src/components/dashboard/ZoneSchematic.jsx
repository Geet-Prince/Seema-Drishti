/**
 * ZoneSchematic.jsx — Mission Control schematic map (MC-5 starter, additive)
 * SVG nodes: green nominal / orange activity(unconfirmed) / red intrusion / grey offline.
 * Click node -> onSelect(zone) opens live snapshot panel. No map tiles (offline-first).
 * Live state via useZoneStatus hook (WebSocket /ws/alerts + GET /api/zones fallback).
 */
const STATUS_COLOR = {
  nominal: "#22c55e",
  activity: "#f59e0b",
  intrusion: "#ef4444",
  offline: "#6b7280",
};

export default function ZoneSchematic({ zones = [], viewBox = "0 0 1000 600", selectedId, onSelect }) {
  return (
    <svg viewBox={viewBox} className="w-full h-auto rounded-xl bg-slate-950 border border-slate-800" role="img" aria-label="Border zone schematic">
      {/* perimeter outline */}
      <rect x={40} y={60} width={920} height={420} rx={18} fill="none" stroke="#334155" strokeDasharray="10 8" strokeWidth={2} />
      <text x={60} y={90} fill="#64748b" fontSize={16} fontFamily="monospace">OUTPOST PERIMETER — SCHEMATIC (OFFLINE)</text>
      {zones.map((z) => {
        const color = STATUS_COLOR[z.status] || STATUS_COLOR.nominal;
        const selected = z.zone_id === selectedId;
        return (
          <g key={z.zone_id} onClick={() => onSelect && onSelect(z)} style={{ cursor: "pointer" }}>
            {z.status !== "nominal" && (
              <circle cx={z.x} cy={z.y} r={26} fill="none" stroke={color} strokeWidth={2} opacity={0.6}>
                <animate attributeName="r" values="20;30;20" dur="1.6s" repeatCount="indefinite" />
                <animate attributeName="opacity" values="0.7;0.15;0.7" dur="1.6s" repeatCount="indefinite" />
              </circle>
            )}
            <circle cx={z.x} cy={z.y} r={14} fill={color} stroke={selected ? "#fff" : "#0f172a"} strokeWidth={selected ? 3 : 2} />
            <text x={z.x} y={z.y - 22} fill="#e2e8f0" fontSize={13} textAnchor="middle" fontFamily="monospace">
              {z.zone_id}
            </text>
            <text x={z.x} y={z.y + 30} fill="#64748b" fontSize={11} textAnchor="middle" fontFamily="monospace">
              {z.camera_id}{z.armed === false ? " · DISARMED" : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
