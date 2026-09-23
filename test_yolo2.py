from ultralytics import YOLO
import numpy as np

model = YOLO("yolov8n.pt")
frames = [np.zeros((416, 416, 3), dtype=np.uint8)]
try:
    res = model.predict(frames, device="mps", workers=0) # without half=True
    print("Test 1 passed")
    res2 = model.predict(frames, device="mps", workers=0, half=True)
    print("Test 2 passed")
except Exception as e:
    print(f"Error: {e}")
