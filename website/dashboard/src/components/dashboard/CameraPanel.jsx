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
  return (
    <section className="flex flex-col gap-4">
      <MainFeed
        cameraId={activeCamera?.id}
        cameraName={activeCamera?.name}
        streamSrc={streamSrc}
        detections={detections}
        offline={!feedOnline}
        humans={humans}
      />

      <div className="hud-panel flex flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-[rgba(0,240,255,0.14)] px-3 py-2">
          <span className="hud-title">▦ Camera Grid</span>
          <span className="mono rounded-sm border border-[rgba(0,240,255,0.25)] bg-[rgba(0,240,255,0.07)] px-1.5 py-0.5 text-[9px] tracking-[0.2em] text-[#00f0ff]">
            {cameras.length} FEED{cameras.length === 1 ? '' : 'S'}
          </span>
        </div>
        <QuadView
          cameras={cameras}
          activeCameraId={activeCamera?.id}
          onSelect={onSelectCamera}
        />
      </div>
    </section>
  );
}
