import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';

const SEV_COLOR = {
  nominal: '#39ff88',
  medium: '#ffb020',
  high: '#ff6b2c',
  critical: '#ff2d55',
  live: '#00f0ff',
};

function Sparkline({ data, color }) {
  if (!data || data.length < 2) return <div className="h-7" />;
  const w = 84;
  const h = 28;
  const max = Math.max(...data, 1);
  const step = w / (data.length - 1);
  const pts = data.map((v, i) => [i * step, h - (v / max) * h]);
  const line = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `${line} L${w},${h} L0,${h} Z`;
  const gid = `sg-${String(color).replace(/[^a-z0-9]/gi, '')}`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.45} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <path d={line} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" style={{ filter: `drop-shadow(0 0 4px ${color})` }} />
      <circle cx={pts[pts.length-1][0]} cy={pts[pts.length-1][1]} r={2.2} fill={color} style={{ filter: `drop-shadow(0 0 5px ${color})` }} />
    </svg>
  );
}

export default function StatCard({ label, value, trend, direction, sparkline, severity, tone = 'neutral' }) {
  const color = SEV_COLOR[severity] || SEV_COLOR.nominal;
  const Arrow = direction === 'up' ? ArrowUpRight : direction === 'down' ? ArrowDownRight : Minus;
  const trendColor = trendTone(tone, direction);
  const hot = severity === 'critical' || severity === 'high';

  return (
    <div
      className="hud-panel group relative flex min-w-[150px] flex-1 flex-col justify-between overflow-hidden p-3 transition-transform duration-200 hover:-translate-y-0.5"
      style={hot ? { borderColor: `${color}55`, boxShadow: `0 0 24px ${color}22, inset 0 1px 0 rgba(255,255,255,0.05)` } : undefined}
    >
      {/* top data bar */}
      <div className="absolute inset-x-0 top-0 h-[2px]" style={{ background: `linear-gradient(90deg, transparent, ${color}aa, transparent)` }} />
      <div className="flex items-center justify-between">
        <span className="hud-label !text-[9px]">{label}</span>
        <span className="flex items-center gap-0.5 mono text-[10px]" style={{ color: trendColor }}>
          {trend != null ? `${direction === 'flat' ? '' : (direction === 'up' ? '+' : '−')}${trend}` : ''}
          {trend != null && <Arrow className="h-3 w-3" />}
        </span>
      </div>
      <div className="mt-2 flex items-end justify-between gap-2">
        <span className="font-display text-[26px] font-bold leading-none tracking-wider" style={{ color, textShadow: `0 0 18px ${color}88` }}>
          {typeof value === 'number' ? value.toLocaleString() : value ?? '—'}
        </span>
        <Sparkline data={sparkline} color={color} />
      </div>
      {/* corner tick */}
      <span className="absolute bottom-1.5 right-2 mono text-[8px] tracking-[0.2em] text-[#5f7a95]/60">◈ LIVE</span>
    </div>
  );
}

function trendTone(tone, direction) {
  if (tone === 'negative') {
    if (direction === 'up') return '#ff2d55';
    if (direction === 'down') return '#39ff88';
    return '#5f7a95';
  }
  if (direction === 'up' || direction === 'down') return '#00f0ff';
  return '#5f7a95';
}
