import { ShieldCheck, Folder, ChevronDown, ChevronRight } from 'lucide-react';
import AlertRow from './AlertRow';
import { useState } from 'react';

function Skeleton({ count = 6 }) {
  return (
    <div className="flex flex-col">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 border-b border-[rgba(0,240,255,0.07)] px-3 py-3">
          <div className="h-2 w-2 animate-pulse rounded-full bg-[rgba(0,240,255,0.25)]" />
          <div className="flex-1 space-y-2">
            <div className="h-3 w-2/3 animate-pulse rounded bg-white/10" />
            <div className="h-2 w-1/2 animate-pulse rounded bg-white/5" />
          </div>
          <div className="h-10 w-10 animate-pulse rounded-sm bg-white/5" />
        </div>
      ))}
    </div>
  );
}

function Empty({ label }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full border border-[rgba(57,255,136,0.3)] bg-[rgba(57,255,136,0.06)]">
        <ShieldCheck className="h-6 w-6 text-[#39ff88]" style={{ filter: 'drop-shadow(0 0 6px rgba(57,255,136,0.8))' }} />
      </div>
      <div>
        <div className="font-display text-[12px] font-semibold tracking-[0.18em] text-white">PERIMETER SECURE</div>
        <div className="mono mt-1 text-[10px] tracking-[0.15em] text-[#5f7a95]">NO ACTIVE {String(label).toUpperCase()} · SCANNING…</div>
      </div>
    </div>
  );
}

function CameraFolder({ cameraId, items, selectedId, onSelect }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="flex flex-col border-b border-[rgba(0,240,255,0.08)] last:border-b-0">
      <button
        onClick={() => setOpen(!open)}
        className="sticky top-0 z-10 flex items-center gap-2 border-y border-[rgba(0,240,255,0.1)] bg-[rgba(2,4,9,0.9)] px-3 py-2 text-left backdrop-blur-md transition-colors hover:bg-[rgba(0,240,255,0.05)]"
      >
        {open ? <ChevronDown className="h-3.5 w-3.5 text-[#00f0ff]" /> : <ChevronRight className="h-3.5 w-3.5 text-[#5f7a95]" />}
        <Folder className="h-3.5 w-3.5 text-[#00f0ff]/70" />
        <span className="mono text-[11px] font-bold tracking-[0.15em] text-white">{cameraId}</span>
        <span className="ml-auto rounded-sm border border-[rgba(0,240,255,0.3)] bg-[rgba(0,240,255,0.1)] px-1.5 py-0.5 mono text-[9px] text-[#00f0ff]">{items.length}</span>
      </button>
      {open && (
        <div className="flex flex-col">
          {items.map((item) => (
            <div key={item._id} className="border-l-2 border-[rgba(0,240,255,0.2)] pl-1">
              <AlertRow item={item} selected={item._id === selectedId} onSelect={onSelect} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AlertList({ items = [], loading = false, selectedId, onSelect, label = 'alerts' }) {
  if (loading) return <div className="max-h-[480px] flex-1 overflow-y-auto"><Skeleton /></div>;
  if (items.length === 0) return <div className="max-h-[480px] flex-1 overflow-y-auto"><Empty label={label} /></div>;

  if (label === 'incidents') {
    const groups = {};
    items.forEach(item => {
      const cam = item.cameraId || 'Unknown';
      if (!groups[cam]) groups[cam] = [];
      groups[cam].push(item);
    });
    return (
      <div className="max-h-[480px] flex-1 overflow-y-auto">
        {Object.entries(groups).map(([cam, groupItems]) => (
          <CameraFolder key={cam} cameraId={cam} items={groupItems} selectedId={selectedId} onSelect={onSelect} />
        ))}
      </div>
    );
  }

  return (
    <div className="max-h-[480px] flex-1 overflow-y-auto">
      {items.map((item) => (
        <AlertRow key={item._id} item={item} selected={item._id === selectedId} onSelect={onSelect} />
      ))}
    </div>
  );
}
