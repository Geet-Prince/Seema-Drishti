# 📦 Downloaded Model Files — SEEMA DRISHTI (IBVAP)

> This document lists every model/weight file downloaded by this project, where it lives, and how to delete it when no longer needed.

---

## 🗂️ External (Outside Project Folder)

These are stored in your macOS home directory and **persist even if you delete the project**.

| Library | Path | Size | What it does |
|---|---|---|---|
| **InsightFace** (buffalo_s) | `~/.insightface/models/buffalo_s/` | ~292 MB | Face detection & recognition (ArcFace model) |
| **InsightFace zip** | `~/.insightface/models/buffalo_s.zip` | ~125 MB | Downloaded archive (can be deleted manually) |
| **DeepFace weights** | `~/.deepface/weights/` | varies | Backup face detection/recognition models |

---

## 🗂️ Inside the Project Folder

These are deleted automatically when you remove the project directory.

| File | Path | Size | What it does |
|---|---|---|---|
| **YOLOv8n** | `ibvap/yolov8n.pt` | ~6.3 MB | Nano object detection (people, vehicles) |
| **YOLOv8s TensorRT Engine** | `ibvap/yolov8s.engine` | ~25 MB | GPU-accelerated detection (NVIDIA only) |
| **Custom border detection model** | `ibvap/human_detection/models/current/best.pt` | ~6.2 MB | Fine-tuned human detection model |
| **DeepSort MobileNetV2 embedder** | `ibvap/venv/.../mobilenetv2_bottleneck_wts.pt` | ~8.7 MB | Person re-identification (tracking) |
| **Ultralytics weights dir** | `ibvap/weights/` | varies | Any cached Ultralytics/YOLO weights |

---

## 📊 Total Estimated Storage Used

| Location | Size |
|---|---|
| External (`~/.insightface/`) | **~292 MB** |
| External (`~/.deepface/`) | varies (0–200 MB) |
| Inside project | **~46 MB** (+ venv) |
| **Total (approx)** | **~340+ MB** |

---

## 🗑️ How to Clean Up

Run the cleanup script:

```bash
bash "/Users/princeraj/code files/projects/ibvap/cleanup_models.sh"
```

Or clean manually:

```bash
# 1. External model caches
rm -rf ~/.insightface/
rm -rf ~/.deepface/

# 2. Delete whole project (removes everything inside)
rm -rf "/Users/princeraj/code files/projects/ibvap"
```

> **Tip:** If you only want to free external space without deleting the project, just run:
> ```bash
> rm -rf ~/.insightface/ ~/.deepface/
> ```

---

## 🔍 Find Any Remaining Model Files

Run this to scan for any leftover `.pt`, `.h5`, or `.onnx` files on your system:

```bash
find ~ -maxdepth 6 \( -name "*.pt" -o -name "*.h5" -o -name "*.onnx" -o -name "*.pb" \) \
  2>/dev/null | grep -v ".Trash" | grep -v ".gemini" | grep -v "node_modules"
```
