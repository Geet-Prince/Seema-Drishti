from ultralytics import YOLO
import numpy as np

model = YOLO("yolov8n.pt")
frames = [np.zeros((416, 416, 3), dtype=np.uint8) for _ in range(4)]
try:
    res = model.predict(frames, device="mps", workers=0)
    print("Test 3 passed")
except Exception as e:
    print(f"Error: {e}")
