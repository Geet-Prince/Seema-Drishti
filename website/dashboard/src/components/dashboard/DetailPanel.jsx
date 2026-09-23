import { MousePointerClick, Flag, CheckCheck, Camera, MapPin, Crosshair, Users, FileDown, Car, User, ShieldAlert } from 'lucide-react';
import { SEV_COLOR, SEV_GLOW } from '../../lib/theme';
import { downloadIncidentReport } from '../../lib/pdfReport';

function Section({ title, accent = '#00f0ff', children }) {
  return (
    <div className="overflow-hidden rounded-sm border border-[rgba(0,240,255,0.14)] bg-black/30">
      <div className="mono flex items-center gap-2 border-b border-[rgba(0,240,255,0.12)] bg-[rgba(0,240,255,0.04)] px-3 py-1.5 text-[9px] tracking-[0.24em] uppercase" style={{ color: accent }}>
        <span className="h-1 w-1 rounded-full" style={{ background: accent, boxShadow: `0 0 6px 1px ${accent}` }} />
        {title}
      </div>
      <div className="p-3">{children}</div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-8 py-16 text-center">
      <div className="relative flex h-16 w-16 items-center justify-center">
        <div className="absolute inset-0 animate-radar-sweep rounded-full border border-dashed border-[rgba(0,240,255,0.35)]" />
        <MousePointerClick className="h-7 w-7 text-[#00f0ff]/60" />
      </div>
      <div className="font-display text-[11px] font-semibold tracking-[0.22em] text-white">AWAITING TARGET</div>
      <div className="mono text-[10px] tracking-[0.15em] text-[#5f7a95]">SELECT CONTACT FROM STREAM</div>
    </div>
  );
}

export default function DetailPanel({ item, onStatusChange }) {
  if (!item) return <EmptyState />;
  const color = SEV_COLOR[item.severity] || SEV_COLOR.informational;
  const glow = SEV_GLOW[item.severity] || SEV_GLOW.informational;
  const pct = Math.min(item.dangerScore ?? 0, 100);
  const isIncident =
    item.kind === 'incident' ||
    item.snapshotCount != null ||
    item.snapshots?.length ||
    item.modules?.length ||
    item.startedAt;

  let attrs = {};
  if (item.attributes) {
    if (typeof item.attributes === 'string') {
      try { attrs = JSON.parse(item.attributes); } catch (e) {}
    } else if (typeof item.attributes === 'object') {
      attrs = item.attributes;
    }
  }

  const hasIdentity = attrs.identity != null || (item.humansDetected > 0);
  const identityName = attrs.identity || 'Unknown';
  const imagePath = attrs.image_path;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 font-display text-[12px] font-bold tracking-[0.06em] text-white">
            <ShieldAlert className="h-3.5 w-3.5 shrink-0" style={{ color }} />
            <span className="truncate">{item.title}</span>
          </div>
          <div className="mt-1 flex items-center gap-1 mono text-[10px] tracking-wider text-[#5f7a95]">
            <MapPin className="h-3 w-3 text-[#00f0ff]/60" />
            {item.location}
          </div>
        </div>
        <span className="shrink-0 rounded-sm px-2 py-1 mono text-[10px] font-bold uppercase tracking-[0.15em] animate-flicker"
          style={{ background: `${color}1f`, color, border: `1px solid ${color}66`, boxShadow: `0 0 14px ${glow}`, textShadow: `0 0 8px ${glow}` }}>
          {item.dangerLabel || item.severity}
        </span>
      </div>

      <Section title="Threat Index" accent={color}>
        <div className="relative">
          <div className="flex items-end justify-between">
            <span className="font-display text-[30px] font-black leading-none" style={{ color, textShadow: `0 0 22px ${glow}` }}>
              {item.dangerScore ?? 0}
            </span>
            <span className="mono text-[9px] tracking-[0.2em] text-[#5f7a95]">/ 100</span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full border border-white/10 bg-black/60">
            <div className="h-full rounded-full transition-all duration-700"
              style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${color}88, ${color})`, boxShadow: `0 0 12px ${glow}` }} />
          </div>
          <div className="mt-1.5 flex items-center justify-between mono text-[9px] tracking-[0.15em] text-[#9db4cc]">
            <span>{item.dangerLabel || '—'}</span>
            {item.confidence != null && <span>CON {item.confidence}%</span>}
          </div>
        </div>
      </Section>

      <Section title="Visual Evidence" accent="#00f0ff">
        {item.snapshots && item.snapshots.length > 0 ? (
          <div className="flex gap-2 overflow-x-auto pb-1">
            {item.snapshots.map((src, i) => (
              <div key={i} className="relative shrink-0">
                <img src={src} alt="snapshot" className="h-28 rounded-sm border border-[rgba(0,240,255,0.3)] object-cover" />
                <span className="absolute bottom-1 left-1 rounded-sm bg-black/70 px-1 mono text-[8px] text-[#00f0ff]">#{String(i + 1).padStart(3, '0')}</span>
              </div>
            ))}
          </div>
        ) : item.snapshotUrl ? (
          <div className="relative">
            <img src={item.snapshotUrl} alt="snapshot" className="max-h-48 w-full rounded-sm border border-[rgba(0,240,255,0.3)] bg-black object-contain" />
            <span className="absolute left-2 top-2 rounded-sm bg-black/70 px-1.5 py-0.5 mono text-[8px] tracking-[0.2em] text-[#00f0ff]">◉ LIVE CAPTURE</span>
          </div>
        ) : (
          <div className="flex h-24 items-center justify-center rounded-sm border border-dashed border-[rgba(0,240,255,0.2)] mono text-[10px] tracking-[0.2em] text-[#5f7a95]">
            // AWAITING CAPTURE
          </div>
        )}
      </Section>

      <Section title="Event Data" accent="#8b5cf6">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[11px]">
          <dt className="mono text-[10px] uppercase tracking-wider text-[#5f7a95]">Incident</dt>
          <dd className="mono truncate text-[11px] text-[#9db4cc]">{item._id}</dd>
          <dt className="mono text-[10px] uppercase tracking-wider text-[#5f7a95]">Camera</dt>
          <dd className="flex items-center gap-1 text-[#e8f4ff]"><Camera className="h-3 w-3 text-[#00f0ff]/60" />{item.cameraName}</dd>
          <dt className="mono text-[10px] uppercase tracking-wider text-[#5f7a95]">Module</dt>
          <dd className="mono text-[#9db4cc]">{item.module || '—'}</dd>
          <dt className="mono text-[10px] uppercase tracking-wider text-[#5f7a95]">Track</dt>
          <dd className="flex items-center gap-1 mono text-[#9db4cc]"><Crosshair className="h-3 w-3 text-[#00f0ff]/60" />{item.trackId || '—'}</dd>
          {hasIdentity && (
            <>
              <dt className="mono text-[10px] uppercase tracking-wider text-[#5f7a95]">Identity</dt>
              <dd className="flex items-center gap-2 font-semibold text-white">
                {identityName !== 'Unknown' && imagePath ? (
                  <img src={imagePath} className="h-6 w-6 rounded-full border border-[#8b5cf6] object-cover" style={{ boxShadow: '0 0 10px rgba(139,92,246,0.6)' }} title={identityName} />
                ) : (
                  <span className="flex h-6 w-6 items-center justify-center rounded-full border border-white/15 bg-white/5 text-[#9db4cc]"><User size={11} /></span>
                )}
                <span>{identityName} {attrs.badge_number ? <span className="mono text-[10px] text-[#8b5cf6]">[{attrs.badge_number}]</span> : ''}</span>
              </dd>
            </>
          )}
          <dt className="mono text-[10px] uppercase tracking-wider text-[#5f7a95]">Timestamp</dt>
          <dd className="mono text-[11px] text-[#9db4cc]">{new Date(item.timestamp).toLocaleString()}</dd>
          {item.humansDetected > 0 && (
            <>
              <dt className="mono text-[10px] uppercase tracking-wider text-[#5f7a95]">Humans</dt>
              <dd className="flex items-center gap-1 font-bold text-[#39ff88]"><Users className="h-3 w-3" />{item.humansDetected}</dd>
            </>
          )}
          {item.vehiclesDetected > 0 && (
            <>
              <dt className="mono text-[10px] uppercase tracking-wider text-[#5f7a95]">Vehicles</dt>
              <dd className="flex items-center gap-1 font-bold text-[#39ff88]"><Car className="h-3 w-3" />{item.vehiclesDetected}</dd>
            </>
          )}
          {(item.plateNumbers?.length > 0 || item.plateNo) && (
            <>
              <dt className="mono text-[10px] uppercase tracking-wider text-[#5f7a95]">Plate</dt>
              <dd className="inline-block w-fit rounded-sm border border-[rgba(0,240,255,0.4)] bg-[rgba(0,240,255,0.1)] px-1.5 py-0.5 mono text-[11px] font-bold text-[#00f0ff]" style={{ textShadow: '0 0 8px rgba(0,240,255,0.8)' }}>
                {item.plateNumbers?.join(', ') || item.plateNo}
              </dd>
            </>
          )}
        </dl>
      </Section>

      {(item.zoneBreaches?.length > 0 || item.activities?.length > 0) && (
        <Section title="Signal Tags" accent="#ffb020">
          <div className="flex flex-wrap gap-1.5">
            {item.zoneBreaches.map((z) => (
              <span key={z} className="rounded-sm border border-[rgba(255,45,85,0.4)] bg-[rgba(255,45,85,0.1)] px-2 py-0.5 mono text-[9px] tracking-wider text-[#ff8fa3]">🚧 {z}</span>
            ))}
            {item.activities.map((a) => (
              <span key={a} className="rounded-sm border border-[rgba(0,240,255,0.3)] bg-[rgba(0,240,255,0.07)] px-2 py-0.5 mono text-[9px] tracking-wider text-[#00f0ff]">◈ {a}</span>
            ))}
          </div>
        </Section>
      )}

      <div className="flex flex-col gap-2">
        {isIncident && (
          <button
            onClick={() => downloadIncidentReport(item)}
            className="flex w-full items-center justify-center gap-1.5 rounded-sm border border-[rgba(0,240,255,0.4)] bg-[rgba(0,240,255,0.08)] px-3 py-2 mono text-[10px] font-bold uppercase tracking-[0.2em] text-[#00f0ff] transition-all hover:bg-[rgba(0,240,255,0.18)] hover:shadow-[0_0_16px_rgba(0,240,255,0.35)]"
          >
            <FileDown className="h-3.5 w-3.5" /> Export Dossier · PDF
          </button>
        )}
        <div className="flex gap-2">
          <button
            onClick={() => onStatusChange?.(item, 'escalated')}
            disabled={item.status === 'escalated'}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-sm border border-[rgba(255,107,44,0.5)] bg-[rgba(255,107,44,0.08)] px-3 py-2 mono text-[10px] font-bold uppercase tracking-[0.15em] text-[#ff6b2c] transition-all hover:bg-[rgba(255,107,44,0.2)] disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Flag className="h-3.5 w-3.5" /> Escalate
          </button>
          <button
            onClick={() => onStatusChange?.(item, 'reviewed')}
            disabled={item.status === 'reviewed'}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-sm border border-[rgba(57,255,136,0.45)] bg-[rgba(57,255,136,0.08)] px-3 py-2 mono text-[10px] font-bold uppercase tracking-[0.15em] text-[#39ff88] transition-all hover:bg-[rgba(57,255,136,0.18)] disabled:cursor-not-allowed disabled:opacity-40"
          >
            <CheckCheck className="h-3.5 w-3.5" /> Reviewed
          </button>
        </div>
      </div>
    </div>
  );
}
