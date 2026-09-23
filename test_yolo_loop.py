import threading
from ultralytics import YOLO
import numpy as np
import time

def run_bg():
    model = YOLO("yolov8n.pt")
    frames = [np.zeros((416, 416, 3), dtype=np.uint8)]
    try:
        for i in range(200):
            res = model.predict(frames, device="mps", verbose=False)
    except Exception as e:
        print(f"Error: {e}")
    print("Loop finished")

t = threading.Thread(target=run_bg)
t.start()
t.join()
