import { Radio, Video } from 'lucide-react';

export default function CameraThumbGrid({ cameras = [], activeCameraId, onSelect }) {
  return (
    <div className="flex flex-col overflow-hidden rounded-lg border border-hairline bg-panel">
      <div className="flex items-center justify-between border-b border-hairline px-3 py-2">
        <span className="mono text-[10px] tracking-[0.2em] uppercase text-ghost">Cameras</span>
        <span className="mono text-[10px] text-ghost">{cameras.length} feed{cameras.length === 1 ? '' : 's'}</span>
      </div>
      
      <div className="grid grid-cols-1 gap-2 p-2">
        {/* "All Cameras" grid tile */}
        <button
          onClick={() => onSelect?.('__grid__')}
          className={`group relative overflow-hidden rounded-md border text-left transition-colors ${
            activeCameraId === '__grid__' ? 'border-live/60' : 'border-hairline hover:border-[rgba(0,240,255,0.28)]'
          }`}
          title="All Cameras Grid View"
        >
          <div className="relative aspect-[4/1] w-full bg-black flex items-center justify-center">
            <Radio className="h-5 w-5 text-live/60" />
            <span className="ml-2 text-ghost uppercase tracking-wider text-xs">Grid View</span>
            {activeCameraId === '__grid__' && (
              <span className="absolute left-2 top-1/2 -translate-y-1/2 h-2 w-2 rounded-full bg-live shadow-[0_0_5px_1px_rgba(74,222,128,0.7)]" />
            )}
          </div>
        </button>
      </div>

      {cameras.length > 0 && (
        <div className="px-2 pb-2">
          <select 
            className="w-full bg-[#0d140e] border border-hairline rounded px-2 py-2 text-sm text-ghost mono uppercase focus:outline-none focus:border-live/50"
            value={activeCameraId !== '__grid__' ? activeCameraId : ""}
            onChange={(e) => {
              if (e.target.value) onSelect?.(e.target.value);
            }}
          >
            <option value="" disabled>Select Camera...</option>
            {cameras.map(cam => (
              <option key={cam.id} value={cam.id}>{cam.name} ({cam.id})</option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
