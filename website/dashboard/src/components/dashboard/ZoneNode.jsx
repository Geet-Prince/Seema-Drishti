/**
 * ZoneNode — single radar node + alert pulse ring (sci-fi neon edition).
 */
const DOT = {
  green: "#39ff88",
  orange: "#ff6b2c",
  red: "#ff2d55",
  offline: "#5f7a95",
};

const LABEL = { green: "Nominal", orange: "Activity", red: "Intrusion", offline: "Offline" };

export default function ZoneNode({ zone, selected, onSelect }) {
  const color = DOT[zone.status] || DOT.green;
  const pulse = (zone.status === "orange" || zone.status === "red") && !zone.ack;
  return (
    <button
      type="button"
      aria-label={`${zone.name} — ${LABEL[zone.status] || zone.status}`}
      onClick={() => onSelect?.(zone.id)}
      className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full transition-transform hover:scale-125"
      style={{ left: zone.x, top: zone.y, width: 15, height: 15 }}
    >
      {pulse && (
        <span aria-hidden className="absolute inset-0 animate-ping rounded-full opacity-50" style={{ background: color }} />
      )}
      {pulse && (
        <span aria-hidden className="absolute inset-0 animate-pulse-ring rounded-full" style={{ border: `2px solid ${color}` }} />
      )}
      <span
        aria-hidden
        className="absolute inset-[3px] rounded-full"
        style={{
          background: color,
          boxShadow: selected ? `0 0 0 2px #fff, 0 0 14px 3px ${color}` : `0 0 10px 2px ${color}`,
        }}
      />
    </button>
  );
}
