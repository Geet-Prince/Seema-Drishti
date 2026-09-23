from ultralytics import YOLO
import numpy as np

model = YOLO("yolov8n.pt")
frames = [np.zeros((416, 416, 3), dtype=np.uint8)]
# See if workers=0 prevents the pin_memory warning
try:
    res = model.predict(frames, device="mps", workers=0)
    print("Success with workers=0")
except Exception as e:
    print(f"Error: {e}")
