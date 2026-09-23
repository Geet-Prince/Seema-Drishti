export default function AlertTabs({ tab, onChange, counts = {} }) {
  const tabs = [
    { id: 'alerts', label: 'Live Alerts', count: counts.alerts },
    { id: 'incidents', label: 'Dossiers', count: counts.incidents },
  ];
  return (
    <div className="flex shrink-0 gap-1 border-b border-[rgba(0,240,255,0.14)] bg-black/30 p-1.5">
      {tabs.map((t) => {
        const active = tab === t.id;
        return (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            className="relative flex flex-1 items-center justify-center gap-2 overflow-hidden rounded-sm px-4 py-2 mono text-[10px] font-bold uppercase tracking-[0.24em] transition-all duration-200"
            style={active
              ? { background: 'rgba(0,240,255,0.12)', color: '#00f0ff', border: '1px solid rgba(0,240,255,0.4)', boxShadow: '0 0 16px rgba(0,240,255,0.2), inset 0 0 12px rgba(0,240,255,0.06)', textShadow: '0 0 10px rgba(0,240,255,0.8)' }
              : { color: '#5f7a95', border: '1px solid transparent' }}
          >
            {active && <span className="absolute inset-x-0 top-0 h-[2px] bg-[#00f0ff] shadow-[0_0_8px_2px_rgba(0,240,255,0.8)]" />}
            {t.label}
            {t.count != null && (
              <span className="rounded-sm px-1.5 py-0.5 mono text-[9px]"
                style={active
                  ? { background: 'rgba(0,240,255,0.2)', color: '#00f0ff' }
                  : { background: 'rgba(255,255,255,0.06)', color: '#5f7a95' }}>
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
