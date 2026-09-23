import { Hexagon, Activity, Users } from 'lucide-react';
import { useClock } from '../../hooks/useClock';

const SECTORS = [
  { id: 'sector-a', label: 'SECTOR A' },
  { id: 'sector-b', label: 'SECTOR B' },
  { id: 'sector-c', label: 'SECTOR C' },
];

function ConnPill({ status }) {
  const live = status === 'live';
  const connecting = status === 'connecting';
  return (
    <div
      className="flex items-center gap-2 rounded-sm border px-3 py-1.5 mono text-[10px] tracking-[0.22em] uppercase backdrop-blur-md"
      style={{
        borderColor: live ? 'rgba(0,240,255,0.5)' : connecting ? 'rgba(255,176,32,0.5)' : 'rgba(255,45,85,0.5)',
        background: live ? 'rgba(0,240,255,0.08)' : connecting ? 'rgba(255,176,32,0.08)' : 'rgba(255,45,85,0.08)',
        color: live ? '#00f0ff' : connecting ? '#ffb020' : '#ff2d55',
        boxShadow: live ? '0 0 18px rgba(0,240,255,0.25), inset 0 0 12px rgba(0,240,255,0.06)' : undefined,
        textShadow: '0 0 8px currentColor',
      }}
    >
      <span className="relative flex h-2 w-2">
        {live && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-60" />}
        <span className={`relative inline-flex h-2 w-2 rounded-full bg-current ${connecting ? 'animate-pulse' : ''}`} />
      </span>
      {live ? '// LIVE UPLINK' : connecting ? '// RE-LINKING' : '// OFFLINE'}
    </div>
  );
}

export default function TopBar({ sector, onSectorChange, connectionStatus, onPersonnelClick }) {
  const now = useClock();
  const time = now.toLocaleTimeString('en-GB', { hour12: false });
  const ms = String(now.getMilliseconds()).padStart(3, '0');
  const date = now.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase();

  return (
    <header className="relative z-20 shrink-0 border-b border-[rgba(0,240,255,0.18)] bg-[rgba(4,8,18,0.92)] backdrop-blur-xl">
      {/* neon top beam */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#00f0ff] to-transparent opacity-80" />
      <div className="absolute inset-x-0 top-0 h-[18px] bg-gradient-to-b from-[rgba(0,240,255,0.08)] to-transparent pointer-events-none" />

      <div className="flex h-16 items-center justify-between gap-4 px-4">
        {/* Brand block */}
        <div className="flex items-center gap-3">
          <div className="relative flex h-10 w-10 items-center justify-center">
            <Hexagon className="absolute h-10 w-10 text-[#00f0ff]/60" strokeWidth={1} />
            <Hexagon className="absolute h-7 w-7 text-[#00f0ff]" strokeWidth={1.5} style={{ filter: 'drop-shadow(0 0 6px rgba(0,240,255,0.9))' }} />
            <Activity className="relative h-4 w-4 text-[#00f0ff]" style={{ filter: 'drop-shadow(0 0 4px rgba(0,240,255,1))' }} />
            <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-[#39ff88] shadow-[0_0_8px_2px_rgba(57,255,136,0.8)] animate-blink-dot" />
          </div>
          <div className="leading-none">
            <div className="font-display text-[16px] font-bold tracking-[0.22em] text-white text-glow-cyan">
              SEEMA<span className="text-[#00f0ff]">DRISHTI</span>
            </div>
            <div className="mono mt-1 text-[9px] tracking-[0.34em] uppercase text-[#5f7a95]">
              Border Intelligence <span className="text-[#00f0ff]/70">◈ v2.0</span>
            </div>
          </div>
          
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          

          <button
            onClick={onPersonnelClick}
            className="group flex items-center gap-2 rounded-sm border border-[rgba(139,92,246,0.4)] bg-[rgba(139,92,246,0.1)] px-3 py-1.5 mono text-[10px] uppercase tracking-[0.18em] text-[#c4b5fd] transition-all hover:border-[#8b5cf6] hover:bg-[rgba(139,92,246,0.2)] hover:shadow-[0_0_16px_rgba(139,92,246,0.4)]"
          >
            <Users className="h-3.5 w-3.5 transition-transform group-hover:scale-110" />
            <span className="hidden sm:inline">Personnel</span>
          </button>

          <div className="hidden items-center gap-3 rounded-sm border border-[rgba(0,240,255,0.2)] bg-black/40 px-3 py-1 text-right leading-tight sm:flex">
            <div>
              <div className="mono text-[15px] font-bold tracking-widest text-white text-glow-cyan">
                {time}<span className="ml-1 text-[10px] text-[#00f0ff]/70">:{ms}</span>
              </div>
              <div className="mono text-[8px] tracking-[0.24em] uppercase text-[#5f7a95]">{date} · UTC</div>
            </div>
          </div>

          <ConnPill status={connectionStatus} />
        </div>
      </div>
    </header>
  );
}
