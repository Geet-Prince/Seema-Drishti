"""
run_live.py  — IBVAP Full Pipeline
===================================
Runs: YOLO Detection → Tracking → AlarmManager → WebSocket Dashboard

Usage:
    Terminal 1:  python run_live.py        (camera + detection pipeline)
    Terminal 2:  python start_server.py    (FastAPI server + dashboard)
    Browser:     http://localhost:8000/ui
"""
import sys
import cv2
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))

from human_detection.inference.detector import HumanDetector
from human_tracking.inference.tracker import HumanTracker
from suspicious_activity.loitering_detector import SuspiciousActivityDetector
from alarm_manager.src.core import AlarmManager

def main():
    print("=" * 55)
    print("  IBVAP Border Intelligence — Live Pipeline")
    print("  Dashboard: http://localhost:8000/ui")
    print("=" * 55)

    import argparse
    parser = argparse.ArgumentParser(description="Run IBVAP Live Pipeline")
    parser.add_argument("--source", type=str, default="0", help="Video source (0 for webcam, or path to video file)")
    args = parser.parse_args()

    detector       = HumanDetector()
    tracker        = HumanTracker()
    suspicious_det = SuspiciousActivityDetector()
    alarm_manager  = AlarmManager()

    # Determine video source
    source = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video source: {source}")
        return

    print(f"Video source open: {source}. Press 'q' to stop.")
    frame_id = 0

    import os
    try:
        import winsound
    except ImportError:
        winsound = None

    def play_sound_alert():
        if sys.platform == "darwin":
            os.system("afplay /System/Library/Sounds/Ping.aiff &")
        elif winsound:
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
        else:
            sys.stdout.write('\a')
            sys.stdout.flush()

    try:
        from face_recognition.core import FaceRecognitionWorker
        face_worker = FaceRecognitionWorker()
        face_worker.start()
    except Exception as e:
        print(f"Face recognition init failed: {e}")
        face_worker = None

    beeped_events = set()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                # Loop video files forever instead of exiting at EOF.
                try:
                    is_file = float(cap.get(cv2.CAP_PROP_FRAME_COUNT)) > 0
                except Exception:
                    is_file = False
                if is_file:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = cap.read()
                if not ret:
                    if is_file:
                        continue  # transient seek hiccup — retry next iteration
                    print("End of video stream or cannot read the frame.")
                    break

            frame_id += 1
            timestamp = datetime.now(timezone.utc)

            # Step 1: Detect humans with YOLO
            det_result = detector.detect(frame, "CAM_LIVE", frame_id, timestamp)

            # Step 2: Track with DeepSORT
            track_result = tracker.track(det_result)

            # Face Recognition Interception
            if face_worker:
                for obj in track_result.objects:
                    if obj.object_type == "human":
                        identity_info = face_worker.get_identity(obj.track_id)
                        if identity_info:
                            obj.attributes['identity'] = identity_info['name']
                            obj.attributes['badge_number'] = identity_info.get('badge_number', '')
                            obj.attributes['image_path'] = identity_info.get('image_path', '')
                        else:
                            obj.attributes['identity'] = "Unknown"
                            # Enqueue crop for identification
                            x1, y1, x2, y2 = obj.bbox
                            # Add 15% padding
                            h, w = frame.shape[:2]
                            w_pad = int((x2 - x1) * 0.15)
                            h_pad = int((y2 - y1) * 0.15)
                            x1_p, y1_p = max(0, x1 - w_pad), max(0, y1 - h_pad)
                            x2_p, y2_p = min(w, x2 + w_pad), min(h, y2 + h_pad)
                            crop = frame[y1_p:y2_p, x1_p:x2_p]
                            if crop.size > 0:
                                face_worker.enqueue_crop(obj.track_id, crop)

            # Step 3: Suspicious Activity Detection (Loitering, Erratic movement, Crowds)
            analyzed_result = suspicious_det.process(track_result)

            # Step 4: Submit to AlarmManager (snapshot + scoring + web broadcast)
            alarm_manager.submit(analyzed_result, frame=frame)

            # Step 5: Draw visuals
            for obj in analyzed_result.objects:
                x1, y1, x2, y2 = obj.bbox
                activity = obj.attributes.get("activity")
                identity = obj.attributes.get("identity", "Unknown")
                
                # Colors: Green for known, Red for suspicious/unknown
                if identity != "Unknown" and not activity:
                    color = (0, 255, 0) # Safe/Known
                else:
                    color = (0, 0, 255) # Threat/Unknown
                    
                human_num = obj.track_id.split('-')[-1]
                
                if identity != "Unknown":
                    base_label = f"[{identity}]"
                else:
                    base_label = f"Human {human_num} [UNKNOWN]"
                    
                label = f"{base_label} [{activity.upper()}]" if activity else base_label

                if activity:
                    for act in activity.split(", "):
                        event_key = f"{obj.track_id}_{act}"
                        if event_key not in beeped_events:
                            beeped_events.add(event_key)
                            play_sound_alert()

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, label, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
                if "centroid" in obj.attributes:
                    cx, cy = obj.attributes["centroid"]
                    cv2.circle(frame, (int(cx), int(cy)), 5, color, -1)

            # Step 6: Show HUD
            cv2.putText(frame,
                f"Humans: {len(analyzed_result.objects)}  Frame: {frame_id}",
                (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (4, 195, 247), 2)

            cv2.imshow("IBVAP Live — Press q to stop", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("Pipeline stopped.")

if __name__ == "__main__":
    main()
