import { MousePointerClick, Flag, CheckCheck, Camera, MapPin, Crosshair, Users, FileDown, Car, User } from 'lucide-react';
import { SEV_COLOR } from '../../lib/theme';
import { downloadIncidentReport } from '../../lib/pdfReport';

function Section({ title, children }) {
  return (
    <div className="overflow-hidden rounded-lg border border-hairline bg-panel">
      <div className="mono border-b border-hairline px-3 py-1.5 text-[9px] tracking-[0.2em] uppercase text-ghost">
        {title}
      </div>
      <div className="p-3">{children}</div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-8 pt-24 text-center">
      <MousePointerClick className="h-9 w-9 text-ghost/40" />
      <div className="text-[13px] font-medium text-fg/70">Select an alert or incident</div>
      <div className="text-[11px] text-ghost">to view detail</div>
    </div>
  );
}

export default function DetailPanel({ item, onStatusChange }) {
  if (!item) return <EmptyState />;
  const color = SEV_COLOR[item.severity] || SEV_COLOR.informational;
  const pct = Math.min(item.dangerScore ?? 0, 100);
  // Detect an incident robustly — `kind` may be missing on older cached items,
  // so also sniff for incident-only fields.
  const isIncident =
    item.kind === 'incident' ||
    item.snapshotCount != null ||
    item.snapshots?.length ||
    item.modules?.length ||
    item.startedAt;

  // Parse attributes to extract identity
  let attrs = {};
  if (item.attributes) {
    if (typeof item.attributes === 'string') {
      try {
        attrs = JSON.parse(item.attributes);
      } catch (e) {}
    } else if (typeof item.attributes === 'object') {
      attrs = item.attributes;
    }
  }
  
  const hasIdentity = attrs.identity != null || item.identity != null || (item.humansDetected > 0);
  const identityName = attrs.identity || item.identity || "Unknown";
  const imagePath = attrs.image_path || item.faceImage;
  const badgeNumber = attrs.badge_number || item.badgeNumber;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[13px] font-semibold text-fg">{item.title}</div>
          <div className="mt-0.5 flex items-center gap-1 text-[10px] text-ghost">
            <MapPin className="h-3 w-3" />
            {item.location}
          </div>
        </div>
        <span
          className="shrink-0 rounded px-1.5 py-0.5 mono text-[10px] font-semibold uppercase tracking-wider"
          style={{ background: `${color}22`, color }}
        >
          {item.dangerLabel || item.severity}
        </span>
      </div>

      <Section title="Threat Score">
        <div className="h-1.5 overflow-hidden rounded-full bg-hairline">
          <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
        </div>
        <div className="mt-1.5 flex items-center justify-between mono text-[10px] text-dim">
          <span>{item.dangerLabel || '—'} · {item.dangerScore ?? 0}/100</span>
          {item.confidence != null && <span>CON {item.confidence}%</span>}
        </div>
      </Section>

      <Section title="Snapshots">
        {item.snapshots && item.snapshots.length > 0 ? (
          <div className="flex gap-2 overflow-x-auto pb-2 custom-scrollbar">
            {item.snapshots.map((src, i) => (
              <img key={i} src={src} alt="snapshot" className="h-32 rounded border border-hairline object-cover" />
            ))}
          </div>
        ) : item.snapshotUrl ? (
          <img src={item.snapshotUrl} alt="snapshot" className="w-full max-h-48 rounded border border-hairline object-contain bg-black" />
        ) : (
          <div className="flex h-24 items-center justify-center rounded border border-dashed border-hairline text-[11px] text-ghost">
            No snapshot yet
          </div>
        )}
      </Section>

      <Section title="Event Data">
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[11px]">
          <dt className="mono text-ghost">Incident</dt>
          <dd className="mono text-dim">{item._id}</dd>
          <dt className="mono text-ghost">Camera</dt>
          <dd className="flex items-center gap-1 text-dim"><Camera className="h-3 w-3 text-ghost" />{item.cameraName}</dd>
          <dt className="mono text-ghost">Module</dt>
          <dd className="text-dim">{item.module || '—'}</dd>
          <dt className="mono text-ghost flex items-center">Track</dt>
          <dd className="flex items-center gap-1 text-dim"><Crosshair className="h-3 w-3 text-ghost" />{item.trackId || '—'}</dd>
          
          {hasIdentity && (
            <>
              <dt className="mono text-ghost flex items-center h-6">Identity</dt>
              <dd className="flex items-center gap-2 text-fg font-medium">
                {identityName !== 'Unknown' && imagePath ? (
                  <img src={imagePath} className="h-5 w-5 rounded-full border border-live object-cover" title={identityName} />
                ) : (
                  <div className="flex h-5 w-5 items-center justify-center rounded-full border border-hairline bg-panel text-dim">
                    <User size={10} />
                  </div>
                )}
                <span>{identityName} {badgeNumber ? `(${badgeNumber})` : ''}</span>
              </dd>
            </>
          )}

          <dt className="mono text-ghost flex items-center">Timestamp</dt>
          <dd className="mono text-dim">{new Date(item.timestamp).toLocaleString()}</dd>
          {item.humansDetected > 0 && (
            <>
              <dt className="mono text-ghost">Humans</dt>
              <dd className="flex items-center gap-1 text-nominal"><Users className="h-3 w-3" />{item.humansDetected}</dd>
            </>
          )}
          {item.vehiclesDetected > 0 && (
            <>
              <dt className="mono text-ghost">Vehicles</dt>
              <dd className="flex items-center gap-1 text-nominal"><Car className="h-3 w-3" />{item.vehiclesDetected}</dd>
            </>
          )}
          {(item.plateNumbers?.length > 0 || item.plateNo) && (
            <>
              <dt className="mono text-ghost">License Plate</dt>
              <dd className="mono text-live font-bold bg-live/10 px-1 rounded inline-block">
                {item.plateNumbers?.join(', ') || item.plateNo}
              </dd>
            </>
          )}
        </dl>
      </Section>

      {(item.zoneBreaches?.length > 0 || item.activities?.length > 0) && (
        <Section title="Tags">
          <div className="flex flex-wrap gap-1.5">
            {item.zoneBreaches.map((z) => (
              <span key={z} className="rounded-full bg-hairline px-2 py-0.5 text-[10px] text-dim">🚧 {z} (Fence Breached)</span>
            ))}
            {item.activities.map((a) => (
              <span key={a} className="rounded-full bg-hairline px-2 py-0.5 text-[10px] text-dim">🔍 {a}</span>
            ))}
          </div>
        </Section>
      )}

      <div className="mt-1 flex flex-col gap-2">
        {isIncident && (
          <button
            onClick={() => downloadIncidentReport(item)}
            className="flex w-full items-center justify-center gap-1.5 rounded-md border border-hairline-2 px-3 py-2 text-[11px] font-medium text-dim transition-colors hover:bg-panel-2 hover:text-fg"
          >
            <FileDown className="h-3.5 w-3.5" />
            Download PDF Report
          </button>
        )}
        <div className="flex gap-2">
          <button
            onClick={() => onStatusChange?.(item, 'escalated')}
            disabled={item.status === 'escalated'}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-md border border-sev-high/50 px-3 py-2 text-[11px] font-medium text-sev-high transition-colors hover:bg-sev-high/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Flag className="h-3.5 w-3.5" />
            Escalate
          </button>
          <button
            onClick={() => onStatusChange?.(item, 'reviewed')}
            disabled={item.status === 'reviewed'}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-md border border-nominal/40 px-3 py-2 text-[11px] font-medium text-nominal transition-colors hover:bg-nominal/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <CheckCheck className="h-3.5 w-3.5" />
            Mark Reviewed
          </button>
        </div>
      </div>
    </div>
  );
}
