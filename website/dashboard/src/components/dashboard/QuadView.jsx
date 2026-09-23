/**
 * QuadView.jsx — full camera picker grid with sci-fi tiles.
 * Snapshot polling to avoid browser connection limits.
 */
import { useState, useEffect } from 'react';

const REFRESH_INTERVAL_MS = 2500;

function CamTile({ cam, isActive, onClick }) {
  const [broken, setBroken] = useState(false);
  const [timestamp, setTimestamp] = useState(Date.now());

  useEffect(() => {
    if (!cam.online) return;
    const interval = setInterval(() => setTimestamp(Date.now()), REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [cam.online]);

  useEffect(() => { setBroken(false); }, [cam.id]);

  const src = `/stream/snapshot/${cam.id}?t=${timestamp}`;

  return (
    <div
      role="button"
      tabIndex={0}
      className="group relative cursor-pointer select-none overflow-hidden rounded-sm transition-all duration-200"
      style={{
        aspectRatio: '16/9',
        background: '#000',
        border: isActive ? '1px solid rgba(0,240,255,0.8)' : '1px solid rgba(0,240,255,0.15)',
        boxShadow: isActive ? '0 0 16px rgba(0,240,255,0.35), inset 0 0 20px rgba(0,240,255,0.06)' : undefined,
      }}
      onClick={onClick}
      onKeyDown={(e) => e.key === 'Enter' && onClick?.()}
    >
      {broken ? (
        <div className="flex h-full w-full flex-col items-center justify-center gap-1 bg-[#020409]">
          <span className="mono text-[9px] uppercase tracking-[0.25em] text-[#5f7a95]/60">◌ Offline</span>
        </div>
      ) : (
        <img src={src} alt={cam.name || cam.id} className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.04]" onError={() => setBroken(true)} />
      )}

      <div className="pointer-events-none absolute inset-0" style={{ background: 'repeating-linear-gradient(to bottom, transparent 0 3px, rgba(0,0,0,0.18) 3px 4px)' }} />

      {isActive && (
        <span className="absolute right-1.5 top-1.5 flex h-2 w-2">
          <span className="absolute h-full w-full animate-ping rounded-full bg-[#00f0ff] opacity-70" />
          <span className="relative h-2 w-2 rounded-full bg-[#00f0ff] shadow-[0_0_8px_2px_rgba(0,240,255,0.8)]" />
        </span>
      )}

      <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-1 bg-gradient-to-t from-black/90 to-transparent px-1.5 pb-1 pt-4">
        <span className="mono truncate text-[8px] uppercase tracking-[0.18em] text-white/85">{cam.name || cam.id}</span>
        {cam.objects != null && (
          <span className="mono flex-shrink-0 text-[8px] tracking-widest text-[#00f0ff]" style={{ textShadow: '0 0 6px rgba(0,240,255,0.8)' }}>{cam.objects} OBJ</span>
        )}
      </div>

      {!cam.online && !broken && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/50 backdrop-blur-[1px]">
          <span className="rounded-sm border border-[rgba(255,45,85,0.5)] bg-[rgba(255,45,85,0.15)] px-2 py-0.5 mono text-[9px] uppercase tracking-[0.2em] text-[#ff8fa3]">Offline</span>
        </div>
      )}
    </div>
  );
}

export default function QuadView({ cameras = [], activeCameraId, onSelect }) {
  const visible = cameras;
  const [isOpen, setIsOpen] = useState(false);

  if (visible.length === 0) {
    return <div className="flex items-center justify-center py-8 mono text-xs text-[#5f7a95]/50">// No cameras detected</div>;
  }

  const activeCam = visible.find(c => c.id === activeCameraId) || visible[0];

  return (
    <div className="flex w-full flex-col">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between border-b border-[rgba(0,240,255,0.14)] bg-[rgba(0,240,255,0.04)] px-3 py-2 transition-colors hover:bg-[rgba(0,240,255,0.09)]"
      >
        <span className="mono text-[11px] tracking-[0.15em] text-[#9db4cc]">
          TGT: <span className="font-bold text-[#00f0ff]" style={{ textShadow: '0 0 8px rgba(0,240,255,0.7)' }}>{activeCam?.name || activeCam?.id || 'None'}</span>
        </span>
        <span className="mono text-[10px] text-[#00f0ff]/60">{isOpen ? '▲' : '▼'}</span>
      </button>

      {isOpen && (
        <div className="grid max-h-[400px] grid-cols-2 gap-1.5 overflow-y-auto bg-black/30 p-2">
          {visible.map((cam) => (
            <CamTile key={cam.id} cam={cam} isActive={cam.id === activeCameraId}
              onClick={() => { onSelect?.(cam.id); setIsOpen(false); }} />
          ))}
        </div>
      )}
    </div>
  );
}
