import threading
from ultralytics import YOLO
import numpy as np

def run_bg():
    model = YOLO("yolov8n.pt")
    frames = [np.zeros((416, 416, 3), dtype=np.uint8) for _ in range(9)]
    try:
        res = model.predict(frames, device="mps") # Notice NO workers=0
        print("Test 9 passed")
    except Exception as e:
        print(f"Error: {e}")

t = threading.Thread(target=run_bg)
t.start()
t.join()
