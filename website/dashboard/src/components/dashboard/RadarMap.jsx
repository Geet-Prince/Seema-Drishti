import { Radar } from 'lucide-react';

const BLIP_COLOR = {
  critical: '#ff2d55',
  high: '#ff6b2c',
  medium: '#ffb020',
  low: '#39ff88',
  nominal: '#39ff88',
  informational: '#00f0ff',
};

export default function RadarMap({ points = [], onSelectPoint, selectedId }) {
  return (
    <div className="hud-panel scanlines flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-[rgba(0,240,255,0.14)] px-3 py-2">
        <span className="flex items-center gap-2">
          <Radar className="h-3.5 w-3.5 text-[#00f0ff]" style={{ filter: 'drop-shadow(0 0 5px rgba(0,240,255,0.9))' }} />
          <span className="hud-title">Sector Coverage</span>
        </span>
        <span className="mono rounded-sm border border-[rgba(0,240,255,0.25)] bg-[rgba(0,240,255,0.07)] px-1.5 py-0.5 text-[9px] tracking-[0.2em] text-[#00f0ff]">
          {points.length} BLIP{points.length === 1 ? '' : 'S'}
        </span>
      </div>

      <div className="relative flex w-full flex-1 items-center justify-center overflow-hidden bg-[#020409]">
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              'linear-gradient(rgba(0,240,255,0.07) 1px, transparent 1px), linear-gradient(90deg, rgba(0,240,255,0.07) 1px, transparent 1px)',
            backgroundSize: '26px 26px',
            maskImage: 'radial-gradient(circle at center, black 20%, transparent 78%)',
          }}
        />

        <div
          className="relative aspect-square w-full max-w-[260px]"
          style={{ backgroundImage: 'radial-gradient(circle at center, rgba(0,240,255,0.12), transparent 68%)' }}
        >
          {[22, 44, 66].map((r) => (
            <div key={r} className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full"
              style={{ width: `${r * 2}%`, height: `${r * 2}%`, border: '1px solid rgba(0,240,255,0.18)', boxShadow: 'inset 0 0 24px rgba(0,240,255,0.04)' }} />
          ))}
          <div className="pointer-events-none absolute left-1/2 top-1/2 h-full w-full -translate-x-1/2 -translate-y-1/2 rounded-full"
            style={{ border: '1px solid rgba(0,240,255,0.45)', boxShadow: '0 0 24px rgba(0,240,255,0.18), inset 0 0 30px rgba(0,240,255,0.05)' }} />

          <div className="pointer-events-none absolute left-1/2 top-0 h-full w-px bg-[rgba(0,240,255,0.16)]" />
          <div className="pointer-events-none absolute left-0 top-1/2 h-px w-full bg-[rgba(0,240,255,0.16)]" />
          <div className="pointer-events-none absolute left-1/2 top-1/2 h-[86%] w-px origin-top rotate-45 bg-[rgba(0,240,255,0.08)]" />
          <div className="pointer-events-none absolute left-1/2 top-1/2 h-[86%] w-px origin-top -rotate-45 bg-[rgba(0,240,255,0.08)]" />

          {/* sweep */}
          <div className="pointer-events-none absolute inset-0 animate-radar-sweep rounded-full"
            style={{
              transformOrigin: '50% 50%',
              background: 'conic-gradient(from 0deg, rgba(0,240,255,0.5), rgba(0,240,255,0.12) 40deg, transparent 80deg)',
              filter: 'drop-shadow(0 0 10px rgba(0,240,255,0.4))',
            }} />
          <div className="pointer-events-none absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#00f0ff] shadow-[0_0_14px_4px_rgba(0,240,255,0.7)]" />

          {/* range labels */}
          <span className="pointer-events-none absolute left-1/2 top-[4%] -translate-x-1/2 mono text-[7px] tracking-[0.2em] text-[#00f0ff]/50">N · 5KM</span>

          {points.map((p) => {
            const color = BLIP_COLOR[p.severity] || BLIP_COLOR.nominal;
            const isSelected = selectedId === p.id;
            const hot = p.severity === 'critical' || p.severity === 'high';
            return (
              <button key={p.id ?? `${p.x}-${p.y}`} type="button" title={p.label || p.id}
                onClick={() => onSelectPoint?.(p.item)}
                className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full transition-transform hover:scale-125"
                style={{ left: `${p.x}%`, top: `${p.y}%`, width: isSelected ? 18 : hot ? 13 : 10, height: isSelected ? 18 : hot ? 13 : 10 }}>
                {hot && <span className="absolute inset-0 animate-ping rounded-full opacity-50" style={{ background: color }} />}
                <span className="absolute inset-0 rounded-full" style={{ background: color, boxShadow: isSelected ? `0 0 0 2px #fff, 0 0 18px 4px ${color}` : `0 0 12px 2px ${color}` }} />
              </button>
            );
          })}
        </div>

        {/* corner readout */}
        <div className="pointer-events-none absolute bottom-1.5 left-2 mono text-[8px] tracking-[0.22em] text-[#00f0ff]/50">SWEEP 3.2S · 360°</div>
        <div className="pointer-events-none absolute bottom-1.5 right-2 mono text-[8px] tracking-[0.22em] text-[#00f0ff]/50">RNG 5.0 KM</div>
      </div>

      <div className="flex items-center justify-center gap-4 border-t border-[rgba(0,240,255,0.14)] bg-black/30 px-3 py-2">
        {[
          { label: 'Low', color: BLIP_COLOR.low },
          { label: 'Med', color: BLIP_COLOR.medium },
          { label: 'High', color: BLIP_COLOR.high },
          { label: 'Crit', color: BLIP_COLOR.critical },
        ].map((l) => (
          <span key={l.label} className="flex items-center gap-1.5 mono text-[9px] uppercase tracking-[0.18em] text-[#5f7a95]">
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: l.color, boxShadow: `0 0 6px 1px ${l.color}` }} />
            {l.label}
          </span>
        ))}
      </div>
    </div>
  );
}
