import threading
from ultralytics import YOLO
import numpy as np

def run_bg():
    model = YOLO("yolov8n.pt")
    frames = [np.zeros((416, 416, 3), dtype=np.uint8)]
    _kwargs = dict(
        source=frames,
        classes=[0, 2, 3, 5, 7],
        conf=0.25,
        imgsz=416,
        device="mps",
        verbose=False,
    )
    for i in range(10):
        res = model.predict(**_kwargs)
    print("Done")

t = threading.Thread(target=run_bg)
t.start()
t.join()
