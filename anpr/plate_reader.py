import easyocr
import re
import cv2

class PlateReader:
    def __init__(self):
        # GPU only for real CUDA (shared probe also catches the
        # NVIDIA-present-but-torch-CPU trap). EasyOCR on MPS/CPU threads
        # races YOLO and aborts macOS, so CPU elsewhere on both platforms.
        try:
            from configs.compute import detect_compute
            use_gpu = detect_compute()["device"].startswith("cuda")
        except Exception:
            import platform
            try:
                import torch
                use_gpu = bool(torch.cuda.is_available() and platform.system() != "Darwin")
            except Exception:
                use_gpu = False
        self.reader = easyocr.Reader(['en'], gpu=use_gpu)
        self.pattern = re.compile(r'[^A-Z0-9]')

    def read_plate(self, frame, bbox=None):
        if bbox is not None:
            x1, y1, x2, y2 = [int(v) for v in bbox]
            h, w = frame.shape[:2]
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(w, x2)
            y2 = min(h, y2)
            crop = frame[y1:y2, x1:x2]
        else:
            crop = frame
            
        if crop.size == 0:
            return None
            
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        results = self.reader.readtext(gray)
        
        best_plate = None
        best_conf = 0
        for (bbox_t, text, prob) in results:
            clean_text = self.pattern.sub('', text.upper())
            if len(clean_text) >= 4 and prob > best_conf:
                best_plate = clean_text
                best_conf = prob
                
        return best_plate if best_conf > 0.3 else None
