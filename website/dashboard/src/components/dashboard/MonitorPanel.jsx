import { useState } from 'react';
import { ScanLine } from 'lucide-react';
import AlertTabs from './AlertTabs';
import AlertList from './AlertList';

export default function MonitorPanel({
  alerts = [],
  incidents = [],
  points = [],
  alertsLoading,
  incidentsLoading,
  selectedId,
  onSelect,
  streamSrc,
}) {
  const [tab, setTab] = useState('alerts');
  const items = tab === 'alerts' ? alerts : incidents;
  const loading = tab === 'alerts' ? alertsLoading : incidentsLoading;

  return (
    <section className="flex min-w-0 flex-col gap-4">
      <div className="flex h-[340px] gap-4">
        {streamSrc && (
          <div className="hud-panel relative flex flex-1 items-center justify-center overflow-hidden">
            <div className="absolute inset-x-0 top-0 z-10 flex items-center gap-2 bg-gradient-to-b from-black/80 to-transparent p-2.5">
              <ScanLine className="h-3.5 w-3.5 text-[#ffb020]" style={{ filter: 'drop-shadow(0 0 5px rgba(255,176,32,0.9))' }} />
              <span className="hud-title !text-[#ffb020]" style={{ textShadow: '0 0 12px rgba(255,176,32,0.6)' }}>AI Target Lock</span>
              <span className="ml-auto flex items-center gap-1.5 mono text-[9px] tracking-[0.2em] text-[#ff2d55]">
                <span className="h-1.5 w-1.5 animate-blink-dot rounded-full bg-[#ff2d55] shadow-[0_0_8px_2px_rgba(255,45,85,0.7)]" /> TRACKING
              </span>
            </div>
            <img src={streamSrc} alt="AI Camera Feed" className="h-full w-full object-contain" />
            <span className="pointer-events-none absolute left-2 top-12 h-5 w-5 border-l-2 border-t-2 border-[#ffb020]" style={{ filter: 'drop-shadow(0 0 5px rgba(255,176,32,0.8))' }} />
            <span className="pointer-events-none absolute right-2 top-12 h-5 w-5 border-r-2 border-t-2 border-[#ffb020]" style={{ filter: 'drop-shadow(0 0 5px rgba(255,176,32,0.8))' }} />
            <span className="pointer-events-none absolute bottom-2 left-2 h-5 w-5 border-b-2 border-l-2 border-[#ffb020]" style={{ filter: 'drop-shadow(0 0 5px rgba(255,176,32,0.8))' }} />
            <span className="pointer-events-none absolute bottom-2 right-2 h-5 w-5 border-b-2 border-r-2 border-[#ffb020]" style={{ filter: 'drop-shadow(0 0 5px rgba(255,176,32,0.8))' }} />
          </div>
        )}
        
      </div>

      <div className="hud-panel flex flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-[rgba(0,240,255,0.14)] px-3 py-2">
          <span className="hud-title">◈ Threat Stream</span>
          <span className="mono flex items-center gap-1.5 text-[9px] tracking-[0.2em] text-[#39ff88]">
            <span className="h-1.5 w-1.5 animate-blink-dot rounded-full bg-[#39ff88] shadow-[0_0_6px_2px_rgba(57,255,136,0.7)]" />
            INTERCEPTING
          </span>
        </div>
        <AlertTabs
          tab={tab}
          onChange={setTab}
          counts={{ alerts: alerts.length, incidents: incidents.length }}
        />
        <AlertList
          items={items}
          loading={loading}
          selectedId={selectedId}
          onSelect={onSelect}
          label={tab}
        />
      </div>
    </section>
  );
}
