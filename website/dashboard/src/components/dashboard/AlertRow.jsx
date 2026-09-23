import { Activity, Camera, MapPin, Clock, FileDown, User } from 'lucide-react';
import { SEV_COLOR, SEV_GLOW, relTime } from '../../lib/theme';
import { downloadIncidentReport } from '../../lib/pdfReport';

export default function AlertRow({ item, selected, onSelect }) {
  const color = SEV_COLOR[item.severity] || SEV_COLOR.informational;
  const glow = SEV_GLOW[item.severity] || SEV_GLOW.informational;
  const thumb = item.snapshotUrl;
  const isIncident =
    item.kind === 'incident' ||
    item.snapshotCount != null ||
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
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(item._id)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onSelect(item._id); }}
      className="relative flex w-full animate-alert-in items-start gap-3 border-b border-[rgba(0,240,255,0.08)] px-3 py-2.5 text-left transition-all duration-150"
      style={selected
        ? { background: 'rgba(0,240,255,0.08)', boxShadow: `inset 2px 0 0 ${color}, 0 0 20px rgba(0,240,255,0.08)` }
        : { boxShadow: 'inset 2px 0 0 transparent' }}
      onMouseEnter={(e) => { if (!selected) e.currentTarget.style.background = 'rgba(0,240,255,0.04)'; }}
      onMouseLeave={(e) => { if (!selected) e.currentTarget.style.background = 'transparent'; }}
    >
      <span className="relative mt-1.5 flex h-2 w-2 shrink-0">
        {(item.severity === 'critical' || item.severity === 'high') && (
          <span className="absolute h-full w-full animate-ping rounded-full opacity-60" style={{ background: color }} />
        )}
        <span className="relative h-2 w-2 rounded-full" style={{ background: color, boxShadow: `0 0 8px 2px ${glow}` }} />
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate font-display text-[11px] font-semibold tracking-[0.08em] text-white">{item.title}</span>
          <span className="shrink-0 rounded-sm px-1.5 py-0.5 mono text-[9px] font-bold uppercase tracking-[0.15em]"
            style={{ background: `${color}22`, color, border: `1px solid ${color}55`, textShadow: `0 0 8px ${glow}` }}>
            {item.dangerLabel || item.severity}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-[#5f7a95]">
          <span className="flex items-center gap-1"><MapPin className="h-2.5 w-2.5 text-[#00f0ff]/60" />{item.location}</span>
          <span className="flex items-center gap-1"><Camera className="h-2.5 w-2.5 text-[#00f0ff]/60" />{item.cameraName}</span>
          <span className="flex items-center gap-1 mono"><Clock className="h-2.5 w-2.5" />{relTime(item.timestamp)}</span>
          {hasIdentity && (
            <span className="flex items-center gap-1 text-[10px] font-semibold text-[#e8f4ff]">
              <span className="text-[#8b5cf6]">◈</span> {identityName} {attrs.badge_number ? `(${attrs.badge_number})` : ''}
            </span>
          )}
          {item.confidence != null && (
            <span className="flex items-center gap-1 mono text-[9px] text-[#9db4cc]">
              <Activity className="h-2.5 w-2.5" /> CON {item.confidence}%
            </span>
          )}
          {item.status && item.status !== 'new' && (
            <span className="rounded-sm border border-white/10 bg-white/5 px-1 mono text-[9px] uppercase tracking-wider text-[#9db4cc]">{item.status}</span>
          )}
          {isIncident && (
            <button
              onClick={(e) => { e.stopPropagation(); downloadIncidentReport(item); }}
              className="ml-auto flex items-center gap-1 rounded-sm border border-[rgba(0,240,255,0.25)] bg-[rgba(0,240,255,0.06)] px-1.5 py-0.5 mono text-[9px] text-[#00f0ff] transition-all hover:bg-[rgba(0,240,255,0.15)]"
              title="Download PDF report"
            >
              <FileDown className="h-2.5 w-2.5" /> PDF
            </button>
          )}
        </div>
      </div>

      {thumb && (
        <div className="flex shrink-0 flex-col items-center gap-1">
          <img src={thumb} alt=""
            className="h-11 w-11 rounded-sm border border-[rgba(0,240,255,0.25)] object-cover"
            style={{ boxShadow: '0 0 10px rgba(0,0,0,0.6)' }}
            onError={(e) => (e.currentTarget.style.display = 'none')} />
          {hasIdentity && (
            identityName !== 'Unknown' && imagePath ? (
              <img src={imagePath} title={identityName}
                className="mt-1 h-7 w-7 rounded-full border border-[#8b5cf6] object-cover"
                style={{ boxShadow: '0 0 10px rgba(139,92,246,0.6)' }}
                onError={(e) => (e.currentTarget.style.display = 'none')} />
            ) : (
              <div className="mt-1 flex h-7 w-7 items-center justify-center rounded-full border border-white/15 bg-white/5 text-[#9db4cc]" title="Unknown Identity">
                <User size={13} />
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}
