import MainFeed from './MainFeed';
import QuadView from './QuadView';

export default function CameraPanel({
  activeCamera,
  cameras,
  detections,
  onSelectCamera,
  feedOnline = true,
  humans,
  streamSrc,
}) {
  const isGrid = activeCamera?.id === '__grid__';

  return (
    <section className="flex flex-col gap-4 h-full">
      {isGrid ? (
        <div className="hud-panel flex flex-col flex-1 h-[600px]">
          <div className="flex items-center justify-between border-b border-[rgba(0,240,255,0.14)] px-3 py-2">
            <span className="hud-title">▦ ALL CAMERAS (AI ACTIVE)</span>
            <span className="mono rounded-sm border border-[rgba(0,240,255,0.25)] bg-[rgba(0,240,255,0.07)] px-1.5 py-0.5 text-[9px] tracking-[0.2em] text-[#00f0ff]">
              {cameras.length} FEED{cameras.length === 1 ? '' : 'S'}
            </span>
          </div>
          <div className="flex-1 p-2 overflow-y-auto">
             <QuadView
                cameras={cameras}
                activeCameraId={activeCamera?.id}
                onSelect={onSelectCamera}
                forceOpen={true}
             />
          </div>
        </div>
      ) : (
        <>
          <div className="flex justify-between items-center mb-[-8px] px-1">
             <button 
                onClick={() => onSelectCamera('__grid__')}
                className="mono text-[10px] tracking-widest text-[#00f0ff] hover:text-white border border-[#00f0ff]/30 px-3 py-1 rounded-sm bg-[#00f0ff]/10 transition-colors"
             >
                ◀ BACK TO GRID
             </button>
          </div>
          <MainFeed
            cameraId={activeCamera?.id}
            cameraName={activeCamera?.name}
            streamSrc={streamSrc}
            detections={detections}
            offline={!feedOnline}
            humans={humans}
          />
        </>
      )}
    </section>
  );
}
