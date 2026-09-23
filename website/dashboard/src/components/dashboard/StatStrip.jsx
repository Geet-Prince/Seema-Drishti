import StatCard from './StatCard';

export default function StatStrip({ stats = [] }) {
  if (stats.length === 0) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-7">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="hud-panel h-[92px] animate-pulse overflow-hidden">
            <div className="absolute inset-y-0 w-1/3 animate-beam bg-gradient-to-r from-transparent via-[rgba(0,240,255,0.12)] to-transparent" />
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-7">
      {stats.map((s) => (
        <StatCard key={s.key} {...s} />
      ))}
    </div>
  );
}
