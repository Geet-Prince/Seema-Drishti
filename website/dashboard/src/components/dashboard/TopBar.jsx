import { RadioTower, ShieldHalf } from 'lucide-react';
import { useClock } from '../../hooks/useClock';

const SECTORS = [
  { id: 'sector-a', label: 'Sector A' },
  { id: 'sector-b', label: 'Sector B' },
  { id: 'sector-c', label: 'Sector C' },
];

function ConnPill({ status }) {
  const live = status === 'live';
  return (
    <div
      className={`flex items-center gap-2 rounded-full border px-3 py-1 mono text-[11px] tracking-wider uppercase ${
        live
          ? 'border-live/40 text-live'
          : status === 'connecting'
            ? 'border-ghost/40 text-ghost'
            : 'border-hairline-2/70 text-ghost'
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          live ? 'bg-live shadow-[0_0_6px_1px_rgba(74,222,128,0.7)]' : status === 'connecting' ? 'bg-ghost animate-pulse' : 'bg-ghost/50'
        }`}
      />
      {live ? 'Live' : status === 'connecting' ? 'Reconnecting' : 'Offline'}
    </div>
  );
}

export default function TopBar({ sector, onSectorChange, connectionStatus, onPersonnelClick, onWatchlistClick }) {
  const now = useClock();
  const time = now.toLocaleTimeString('en-GB', { hour12: false });
  const date = now.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short' });

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-hairline bg-panel px-4">
      <div className="flex items-center gap-3">
        <div className="relative">
          <ShieldHalf className="h-5 w-5 text-live" />
          <RadioTower className="absolute -right-1 -top-1 h-2.5 w-2.5 text-nominal" />
        </div>
        <div className="leading-none">
          <div className="text-[15px] font-semibold tracking-wide text-fg">SEEMA DRISHTI</div>
          <div className="mono text-[10px] tracking-[0.25em] uppercase text-ghost">Army Border Intelligence</div>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2">
          <span className="mono text-[10px] tracking-[0.2em] uppercase text-ghost">Sector</span>
          <select
            value={sector}
            onChange={(e) => onSectorChange(e.target.value)}
            className="rounded border border-hairline bg-panel-2 px-2 py-1 mono text-[11px] uppercase tracking-wider text-fg outline-none focus:border-live/50"
          >
            {SECTORS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        <button 
          onClick={onPersonnelClick}
          className="rounded border border-hairline bg-panel-2 px-3 py-1 text-[11px] font-semibold text-fg hover:bg-white/5 transition-colors uppercase tracking-wider mono flex items-center gap-2"
        >
          <span className="hidden sm:inline">Manage</span> Personnel
        </button>

        <button
          onClick={onWatchlistClick}
          className="rounded border border-sev-critical/40 bg-panel-2 px-3 py-1 text-[11px] font-semibold text-sev-critical hover:bg-sev-critical/10 transition-colors uppercase tracking-wider mono flex items-center gap-2"
        >
          <span className="hidden sm:inline">Plate</span> Watchlist
        </button>

        <div className="rounded border border-hairline bg-panel-2 px-3 py-1 text-right leading-tight">
          <div className="mono text-[13px] font-semibold text-fg">{time}</div>
          <div className="mono text-[9px] tracking-[0.15em] uppercase text-ghost">{date} UTC</div>
        </div>

        <ConnPill status={connectionStatus} />
      </div>
    </header>
  );
}
