import { useState, useRef, useEffect, useCallback } from 'react';
import { VideoOff, Edit3, Save, Trash2, Crosshair, Maximize2 } from 'lucide-react';
import { useClock } from '../../hooks/useClock';
import { liveStreamUrl, API_BASE } from '../../lib/config';

const BOX_COLOR = {
  critical: '#ff2d55',
  high: '#ff6b2c',
  medium: '#ffb020',
  low: '#39ff88',
  nominal: '#39ff88',
  informational: '#00f0ff',
};

function Corner({ className, style }) {
  return <span className={`pointer-events-none absolute h-5 w-5 border-[#00f0ff] ${className}`} style={{ filter: 'drop-shadow(0 0 5px rgba(0,240,255,0.9))', ...style }} />;
}

export default function MainFeed({ cameraId, streamSrc, detections = [], cameraName, offline = false, humans }) {
  const [dims, setDims] = useState(null);
  const [streamBroken, setStreamBroken] = useState(false);
  const [isEditingFence, setIsEditingFence] = useState(false);
  const [polygon, setPolygon] = useState([]);
  const [editDims, setEditDims] = useState(null);

  const imgRef = useRef(null);
  const editRef = useRef(null);

  useEffect(() => {
    if (isEditingFence && cameraId) {
      fetch(`${API_BASE}/api/cameras/${cameraId}/fence`)
        .then(res => res.json())
        .then(data => {
          if (data.polygon && data.polygon.length > 0) setPolygon(data.polygon);
          else setPolygon([]);
        })
        .catch(console.error);
    }
  }, [isEditingFence, cameraId]);

  const handleEditorClick = useCallback((e) => {
    if (!editRef.current) return;
    const rect = editRef.current.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    if (px < 0 || py < 0 || px > rect.width || py > rect.height) return;
    if (editDims) {
      const scaleX = editDims.nw / rect.width;
      const scaleY = editDims.nh / rect.height;
      setPolygon(prev => [...prev, [Math.round(px * scaleX), Math.round(py * scaleY)]]);
    } else {
      setPolygon(prev => [...prev, [Math.round(px), Math.round(py)]]);
    }
  }, [editDims]);

  const removeLastPoint = () => setPolygon(prev => prev.slice(0, -1));

  const savePolygon = async () => {
    if (!cameraId) return;
    try {
      await fetch(`${API_BASE}/api/cameras/${cameraId}/fence`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ polygon })
      });
      setIsEditingFence(false);
    } catch (e) {
      console.error(e);
    }
  };

  const now = useClock(1000);
  const time = now.toLocaleTimeString('en-GB', { hour12: false });

  const src = streamSrc ?? liveStreamUrl();
  const ratio = dims ? `${dims.nw} / ${dims.nh}` : '16 / 9';
  const humansCount = humans != null ? humans : null;
  const down = offline || streamBroken;

  return (
    <div className="hud-panel scanlines flex flex-col overflow-hidden">
      {/* header */}
      <div className="flex items-center justify-between border-b border-[rgba(0,240,255,0.14)] px-3 py-2">
        <span className="hud-title">◉ Live Feed</span>
        <span className="flex items-center gap-2">
          <span className="mono max-w-[140px] truncate text-[10px] uppercase tracking-[0.15em] text-[#9db4cc]">{cameraName || cameraId || 'All Cameras'}</span>
          <span className="flex items-center gap-1.5 rounded-sm border border-[rgba(0,240,255,0.2)] bg-black/40 px-1.5 py-0.5">
            <span className={`h-1.5 w-1.5 rounded-full ${down ? 'bg-[#ff2d55]' : 'bg-[#39ff88] animate-blink-dot shadow-[0_0_6px_2px_rgba(57,255,136,0.7)]'}`} />
            <span className="mono text-[10px] tracking-widest text-[#9db4cc]">{time}</span>
          </span>
        </span>
      </div>

      <div className="relative w-full overflow-hidden bg-black" style={{ aspectRatio: ratio }}>
        {down ? (
          <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-[#020409]">
            <div
              className="absolute inset-0 opacity-40"
              style={{ backgroundImage: 'linear-gradient(rgba(0,240,255,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(0,240,255,0.06) 1px, transparent 1px)', backgroundSize: '32px 32px' }}
            />
            <VideoOff className="h-8 w-8 text-[#5f7a95]/50" />
            <span className="mono text-[10px] tracking-[0.3em] uppercase text-[#5f7a95]">// Signal lost — holding last frame</span>
          </div>
        ) : (
          <img
            ref={imgRef}
            key={src}
            src={src}
            alt="live"
            className="h-full w-full object-contain"
            onLoad={(e) => {
              const el = e.currentTarget;
              setStreamBroken(false);
              setDims({ nw: Math.max(el.naturalWidth, 1), nh: Math.max(el.naturalHeight, 1) });
            }}
            onError={() => setStreamBroken(true)}
          />
        )}

        {!down && (
          <>
            {/* HUD frame corners */}
            <Corner className="left-2 top-2 border-l-2 border-t-2" />
            <Corner className="right-2 top-2 border-r-2 border-t-2" />
            <Corner className="bottom-2 left-2 border-b-2 border-l-2" />
            <Corner className="bottom-2 right-2 border-b-2 border-r-2" />
            {/* travelling scan beam */}
            <div className="pointer-events-none absolute inset-x-0 h-[64px] animate-scan-y bg-gradient-to-b from-transparent via-[rgba(0,240,255,0.09)] to-transparent" />
            {/* center reticle */}
            <Crosshair className="pointer-events-none absolute left-1/2 top-1/2 h-10 w-10 -translate-x-1/2 -translate-y-1/2 text-[#00f0ff]/25" strokeWidth={1} />
          </>
        )}

        {cameraId && !isEditingFence && (
          <div className="absolute right-2 top-2 flex gap-1.5">
            <button
              onClick={() => setIsEditingFence(true)}
              className="rounded-sm border border-[rgba(0,240,255,0.3)] bg-black/60 p-1.5 text-[#00f0ff] backdrop-blur-md transition-all hover:bg-[rgba(0,240,255,0.2)] hover:shadow-[0_0_12px_rgba(0,240,255,0.5)]"
              title="Edit Virtual Fence"
            >
              <Edit3 className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {/* top-left telemetry chips */}
        <div className="pointer-events-none absolute left-2 top-2 flex flex-col gap-1.5">
          <span
            className="rounded-sm px-2 py-0.5 mono text-[9px] tracking-[0.2em] backdrop-blur-md"
            style={{
              background: down ? 'rgba(255,45,85,0.2)' : 'rgba(255,45,85,0.16)',
              border: '1px solid rgba(255,45,85,0.5)',
              color: '#ff8fa3',
              textShadow: '0 0 8px rgba(255,45,85,0.9)',
            }}
          >
            ● {down ? 'OFFLINE' : 'REC'}
          </span>
          <span className="w-max rounded-sm border border-[rgba(0,240,255,0.35)] bg-black/60 px-2 py-0.5 mono text-[9px] tracking-[0.2em] text-[#00f0ff] backdrop-blur-md" style={{ textShadow: '0 0 8px rgba(0,240,255,0.9)' }}>
            CONTACTS: {humansCount != null ? humansCount : '--'}
          </span>
          {detections.length > 0 && (
            <span className="w-max rounded-sm border border-[rgba(255,176,32,0.4)] bg-black/60 px-2 py-0.5 mono text-[9px] tracking-[0.2em] text-[#ffb020] backdrop-blur-md">
              TRACKS: {detections.length}
            </span>
          )}
        </div>

        {/* detection boxes */}
        {dims && !down && detections.length > 0 && detections.map((d, i) => {
          const c = BOX_COLOR[d.severity] || BOX_COLOR.nominal;
          return (
            <div
              key={i}
              className="absolute"
              style={{
                left: `${((d.x / dims.nw) * 100).toFixed(2)}%`,
                top: `${((d.y / dims.nh) * 100).toFixed(2)}%`,
                width: `${((d.w / dims.nw) * 100).toFixed(2)}%`,
                height: `${((d.h / dims.nh) * 100).toFixed(2)}%`,
                border: `1.5px solid ${c}`,
                boxShadow: `0 0 14px ${c}66, inset 0 0 14px ${c}22`,
              }}
            >
              <span className="absolute -left-px -top-px h-2.5 w-2.5 border-l-2 border-t-2" style={{ borderColor: '#fff' }} />
              <span className="absolute -right-px -top-px h-2.5 w-2.5 border-r-2 border-t-2" style={{ borderColor: '#fff' }} />
              <span
                className="absolute left-0 top-0 -translate-y-full whitespace-nowrap rounded-t-sm px-1.5 py-px mono text-[9px] font-bold uppercase tracking-wider"
                style={{ background: c, color: '#020409', boxShadow: `0 0 10px ${c}` }}
              >
                {d.label}{d.confidence != null ? ` ${Math.round(d.confidence * 100)}%` : ''}
              </span>
            </div>
          );
        })}

        {/* bottom data strip */}
        {!down && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/85 to-transparent px-3 pb-1.5 pt-5">
            <span className="mono text-[8px] tracking-[0.24em] text-[#00f0ff]/70">AI CORE: YOLOv8s · TRT-FP16 · 9.4MS</span>
            <span className="flex items-center gap-1 mono text-[8px] tracking-[0.24em] text-[#5f7a95]">
              <Maximize2 className="h-2.5 w-2.5" /> {dims ? `${dims.nw}×${dims.nh}` : 'SYNC…'}
            </span>
          </div>
        )}
      </div>

      {/* fence editor modal */}
      {isEditingFence && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4 backdrop-blur-md sm:p-10">
          <div className="hud-panel flex max-h-full w-full max-w-5xl flex-col overflow-hidden" style={{ maxHeight: '92vh' }}>
            <div className="flex items-center justify-between border-b border-[rgba(0,240,255,0.14)] bg-black/40 px-4 py-3">
              <div className="flex flex-col">
                <span className="hud-title">Restricted Zone Editor — {cameraName || cameraId}</span>
                <span className="mono mt-1 text-[10px] text-[#5f7a95]">
                  Click image to add points · right-click undoes · need ≥3 ({polygon.length} pts)
                </span>
              </div>
              <div className="flex shrink-0 gap-2">
                <button onClick={removeLastPoint} disabled={polygon.length === 0}
                  className="rounded-sm border border-[rgba(255,176,32,0.4)] bg-[rgba(255,176,32,0.12)] px-3 py-1.5 mono text-[10px] uppercase tracking-widest text-[#ffb020] hover:bg-[rgba(255,176,32,0.25)] disabled:cursor-not-allowed disabled:opacity-40">
                  Undo
                </button>
                <button onClick={() => setPolygon([])}
                  className="flex items-center gap-1.5 rounded-sm border border-[rgba(255,45,85,0.4)] bg-[rgba(255,45,85,0.12)] px-3 py-1.5 mono text-[10px] uppercase tracking-widest text-[#ff8fa3] hover:bg-[rgba(255,45,85,0.25)]">
                  <Trash2 className="h-3.5 w-3.5" /> Clear
                </button>
                <button onClick={savePolygon} disabled={polygon.length > 0 && polygon.length < 3}
                  className="flex items-center gap-1.5 rounded-sm border border-[rgba(57,255,136,0.45)] bg-[rgba(57,255,136,0.14)] px-3 py-1.5 mono text-[10px] uppercase tracking-widest text-[#39ff88] hover:bg-[rgba(57,255,136,0.28)] disabled:cursor-not-allowed disabled:opacity-40">
                  <Save className="h-3.5 w-3.5" /> Deploy
                </button>
                <button onClick={() => setIsEditingFence(false)}
                  className="rounded-sm border border-white/15 bg-white/5 px-3 py-1.5 mono text-[10px] uppercase tracking-widest text-white hover:bg-white/15">
                  Abort
                </button>
              </div>
            </div>

            <div className="relative flex flex-1 items-center justify-center overflow-hidden bg-black" style={{ minHeight: 0 }}>
              <div className="relative flex h-full w-full items-center justify-center">
                <div className="relative" style={{ aspectRatio: editDims ? `${editDims.nw} / ${editDims.nh}` : '16 / 9', maxWidth: '100%', maxHeight: '100%' }}>
                  <img
                    ref={editRef}
                    src={src}
                    alt="fence editor"
                    className="block h-full w-full cursor-crosshair select-none"
                    draggable={false}
                    onLoad={(e) => {
                      const el = e.currentTarget;
                      setEditDims({ nw: Math.max(el.naturalWidth, 1), nh: Math.max(el.naturalHeight, 1) });
                    }}
                    onClick={handleEditorClick}
                    onContextMenu={(e) => { e.preventDefault(); removeLastPoint(); }}
                  />
                  <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox={editDims ? `0 0 ${editDims.nw} ${editDims.nh}` : '0 0 1 1'} preserveAspectRatio="none">
                    {polygon.length >= 3 && (
                      <polygon points={polygon.map(p => `${p[0]},${p[1]}`).join(' ')} fill="rgba(0,240,255,0.12)" stroke="#00f0ff" strokeWidth={editDims ? editDims.nw * 0.003 : 3} strokeLinejoin="round" style={{ filter: 'drop-shadow(0 0 6px rgba(0,240,255,0.8))' }} />
                    )}
                    {polygon.length >= 2 && (
                      <polyline points={polygon.map(p => `${p[0]},${p[1]}`).join(' ')} fill="none" stroke="#00f0ff" strokeWidth={editDims ? editDims.nw * 0.003 : 3} strokeDasharray={polygon.length < 3 ? '8 4' : 'none'} />
                    )}
                    {polygon.map((p, i) => (
                      <g key={i}>
                        <circle cx={p[0]} cy={p[1]} r={editDims ? editDims.nw * 0.008 : 6} fill={i === 0 ? '#39ff88' : '#00f0ff'} stroke="white" strokeWidth={editDims ? editDims.nw * 0.002 : 2} />
                        <text x={p[0] + (editDims ? editDims.nw * 0.012 : 8)} y={p[1] - (editDims ? editDims.nh * 0.012 : 8)} fill="white" fontSize={editDims ? editDims.nw * 0.018 : 14} fontFamily="monospace" fontWeight="bold">{i === 0 ? 'START' : i}</text>
                      </g>
                    ))}
                  </svg>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
