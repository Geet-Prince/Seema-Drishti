"""
main.py
-------
AI Border Surveillance - YOLO tracking + crossing-event sound alert
that keeps beeping for up to 1 minute so it can't be missed.
"""

import cv2
import json
import argparse
import time
import threading
import numpy as np
import sys
import os

try:
    import winsound
    def play_beep():
        winsound.Beep(1500, 400)
except ImportError:
    def play_beep():
        if sys.platform == "darwin":
            os.system("afplay /System/Library/Sounds/Ping.aiff &")
        else:
            sys.stdout.write('\a')
            sys.stdout.flush()
from datetime import datetime

from ultralytics import YOLO


def load_roi(path, frame_w, frame_h):
    with open(path, "r") as f:
        config = json.load(f)

    cal_w = config["frame_width"]
    cal_h = config["frame_height"]
    raw_points = config["polygon"]

    sx = frame_w / cal_w
    sy = frame_h / cal_h
    polygon = [(int(x * sx), int(y * sy)) for (x, y) in raw_points]
    return polygon


def get_foot_point(box_xyxy):
    x1, y1, x2, y2 = box_xyxy
    foot_x = int((x1 + x2) / 2)
    foot_y = int(y2)
    return foot_x, foot_y


def is_inside_restricted_zone(foot_point, polygon):
    contour = np.array(polygon, dtype="int32")
    result = cv2.pointPolygonTest(contour, foot_point, measureDist=False)
    return result >= 0


def draw_zone(frame, polygon, intrusion_active):
    pts = np.array(polygon, dtype="int32")

    overlay = frame.copy()
    fill_color = (0, 0, 255) if intrusion_active else (0, 0, 120)
    cv2.fillPoly(overlay, [pts], fill_color)
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)

    cv2.polylines(frame, [pts], isClosed=True, color=(0, 0, 255), thickness=3)

    cv2.putText(frame, "SAFE AREA", (40, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 0), 2)
    cv2.putText(frame, "RESTRICTED AREA",
                (40, frame.shape[0] - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 255), 2)


def draw_person(frame, box_xyxy, foot_point, inside, track_id):
    x1, y1, x2, y2 = map(int, box_xyxy)
    color = (0, 0, 255) if inside else (0, 255, 0)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.circle(frame, foot_point, 6, color, -1)
    label = f"INTRUSION (ID {track_id})" if inside else f"person {track_id}"
    cv2.putText(frame, label, (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


def draw_alert_banner(frame):
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w, 60), (0, 0, 255), -1)
    cv2.putText(frame, "!!! INTRUSION DETECTED !!!", (w // 2 - 220, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)


# --------------------------------------------------------------------------- #
# [NEW] Continuous alarm: beeps repeatedly for ALERT_DURATION seconds so it
# can't be missed, instead of a single short beep.
# --------------------------------------------------------------------------- #
ALERT_DURATION = 60        # total seconds the alarm keeps beeping
BEEP_GAP = 1.5              # seconds between individual beeps

alert_active = False        # prevents multiple overlapping alarm threads


def _alarm_loop():
    global alert_active
    alert_active = True
    end_time = time.time() + ALERT_DURATION
    while time.time() < end_time:
        play_beep()
        time.sleep(BEEP_GAP)
    alert_active = False


def trigger_alarm():
    # Agar ek alarm pehle se chal raha hai, dobara naya thread mat banao
    global alert_active
    if not alert_active:
        threading.Thread(target=_alarm_loop, daemon=True).start()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="video.mp4")
    parser.add_argument("--roi", default="roi_config.json")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--conf", type=float, default=0.4)
    args = parser.parse_args()

    source = int(args.source) if str(args.source).isdigit() else args.source
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video source: {source}")

    ret, first_frame = cap.read()
    if not ret:
        raise RuntimeError("Could not read first frame.")
    h, w = first_frame.shape[:2]
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    polygon = load_roi(args.roi, w, h)
    print(f"Loaded ROI polygon (scaled to {w}x{h}): {polygon}")

    model = YOLO(args.model)
    PERSON_CLASS_ID = 0

    previous_state = {}

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model.track(frame, verbose=False, conf=args.conf,
                               classes=[PERSON_CLASS_ID], persist=True)

        intrusion_active = False
        crossed_this_frame = False

        for result in results:
            if result.boxes.id is None:
                continue

            for box, track_id in zip(result.boxes, result.boxes.id):
                xyxy = box.xyxy[0].tolist()
                tid = int(track_id)
                foot_point = get_foot_point(xyxy)
                inside_now = is_inside_restricted_zone(foot_point, polygon)

                if inside_now:
                    intrusion_active = True

                was_inside = previous_state.get(tid, False)

                if inside_now and not was_inside:
                    crossed_this_frame = True

                previous_state[tid] = inside_now

                draw_person(frame, xyxy, foot_point, inside_now, tid)

        draw_zone(frame, polygon, intrusion_active)

        if intrusion_active:
            draw_alert_banner(frame)

        if crossed_this_frame:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[ALERT] {ts} - Person just crossed into restricted area!")
            trigger_alarm()   # [CHANGED] ab 1 minute tak beep chalega

        cv2.imshow("AI Border Surveillance", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()