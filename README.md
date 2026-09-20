<div align="center">

<h1>🛡️ IBVAP — Intelligent Border Video Analytics Platform</h1>
<h3><em>"Turning Commodity Border Cameras into Autonomous Guardians"</em></h3>

<br/>

[![SIH 2026](https://img.shields.io/badge/Smart%20India%20Hackathon-2026-orange?style=for-the-badge)](https://www.sih.gov.in/)
[![SSB](https://img.shields.io/badge/Client-Sashastra%20Seema%20Bal-darkgreen?style=for-the-badge)](https://ssb.nic.in/)
[![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)](https://python.org)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-TensorRT%20FP16-purple?style=for-the-badge)](https://ultralytics.com)
[![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react)](https://reactjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-ASGI-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

<br/>

**Real-Time · Edge-Native · Zero Cloud Dependency · 14+ Camera Streams · 30+ FPS**

</div>

---

## 📑 Table of Contents

1. [What is IBVAP?](#-what-is-ibvap)
2. [The Problem We Solve](#-the-problem-we-solve)
3. [Our Solution at a Glance](#-our-solution-at-a-glance)
4. [System Architecture & Data Flow](#-system-architecture--data-flow)
5. [Module Breakdown](#-module-breakdown)
6. [The Universal Data Contract](#-the-universal-data-contract)
7. [Threat Scoring Engine](#-threat-scoring-engine)
8. [Storage & Evidence Management](#-storage--evidence-management)
9. [Mission Control Dashboard](#-mission-control-dashboard)
10. [REST API & WebSocket Reference](#-rest-api--websocket-reference)
11. [Performance Benchmarks](#-performance-benchmarks)
12. [How to Run the Project](#-how-to-run-the-project)
13. [Project Structure](#-project-structure)
14. [Technology Stack](#-technology-stack)
15. [Feasibility & Economics](#-feasibility--economics)
16. [Team](#-team)

---

## 🎯 What is IBVAP?

**IBVAP (Intelligent Border Video Analytics Platform)** is an **edge-native, real-time multi-camera video intelligence system** engineered for the **Sashastra Seema Bal (SSB)** border outposts of India.

It converts **existing legacy CCTV cameras and RTSP feeds** into an autonomous threat-detection mesh — no proprietary hardware, no cloud dependency, no operator required.

### Key Capabilities at a Glance

| Capability | Detail |
|---|---|
| 🎥 Multi-Camera Processing | 14+ simultaneous RTSP/USB feeds on a single edge GPU |
| 🤖 AI Human Detection | TensorRT FP16 YOLOv8s — `<10ms` inference latency |
| 🏃 Real-Time Tracking | Per-camera stable IDs with velocity vectors |
| 🚗 Vehicle Detection + ANPR | Detect car/truck/bike + read license plates asynchronously |
| 🔴 Virtual Fence Breach | Polygon-based perimeter with click-calibration tool |
| 🧠 Behavioral AI | Loitering, erratic movement, crowd formation detection |
| 👤 Face Recognition | InsightFace ArcFace — known vs unknown personnel identification |
| 📊 Threat Scoring | Dynamic 0–100 score from multi-factor rules (no hardcoded alerts) |
| 🗄️ Evidence Dossiers | Auto-grouped per-incident snapshots + JSON metadata |
| 📡 Live Dashboard | React 19 + WebSocket real-time command center |
| 📄 PDF Reports | One-click forensic PDF export directly from the browser |

---

## 🚨 The Problem We Solve

Border security forces (SSB, BSF, ITBP) guard thousands of kilometers of hostile terrain — riverine gaps, dense vegetation, and porous unfenced stretches.

### Critical Pain Points of Existing Infrastructure

1. **Operator Fatigue**: Studies show human surveillance operators miss **up to 95% of screen activity** after just 22 minutes of continuous multi-screen monitoring.

2. **Proprietary Hardware Lock-In**: Traditional defense video analytics solutions cost **₹15,00,000 – ₹40,00,000 ($20k–$50k) per outpost**, with recurring licensing fees and vendor dependency.

3. **False Alarm Fatigue**: Simple motion detection triggers **hundreds of false alarms daily** due to swaying trees, wandering wildlife, rain, and shadow shifts — desensitizing operators to real threats.

4. **High Bandwidth & Cloud Dependency**: Transmitting 14+ HD RTSP streams to a central cloud over unreliable tactical border networks causes massive bandwidth choking and catastrophic latency.

5. **Disjointed Forensic Records**: Detections are logged as isolated events without continuous tracking, face/plate correlation, or grouped evidence timelines — making post-event investigation extremely difficult.

---

## 💡 Our Solution at a Glance

```
┌─────────────────────────────────────────────────────────────────────┐
│                              IBVAP                                   │
│        "Turning Commodity Border Cameras into Autonomous Guardians"  │
├─────────────────────────────────────────────────────────────────────┤
│  ✓ 14+ Concurrent Cameras processed on 1 Edge GPU                  │
│  ✓ <10ms TensorRT FP16 Neural Inference Latency                     │
│  ✓ 0–100 Dynamic Multi-Factor Threat Scoring                        │
│  ✓ Automatic Grouped Evidence Incident Dossiers                     │
│  ✓ 1-Click Forensic PDF Reports                                     │
│  ✓ Zero Proprietary Hardware Lock-In (100% Open Source)            │
│  ✓ 100% Offline — No Internet or Cloud Required                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ System Architecture & Data Flow

The entire pipeline executes inside a single process (`run_ibvap.py`), with every camera stream handled by a dedicated thread. Here is the exact flow of data from pixel to alert:

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                               IBVAP — Full Data Flow                                │
└─────────────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────┐
  │          STEP 1: Edge Video Ingestion               │
  │  Camera 1 (Gate) ──────────────────────┐           │
  │  Camera 2 (Fence) ─────────────────────┤ RTSP/MP4  │
  │  Camera N (Road) ──────────────────────┘           │
  │             ↓  ThreadedCamera Matrix (14 feeds)     │
  └─────────────────────────────────────────────────────┘
                        │
                        ▼
  ┌─────────────────────────────────────────────────────┐
  │          STEP 2: Batched AI Inference Core           │
  │                                                     │
  │  Frames from all cameras → batched together         │
  │       ↓                                             │
  │  YOLOv8s Engine (TensorRT FP16, <10ms/batch)        │
  │       ↓                                             │
  │  Detections → SimpleIOUTracker (per-camera state)   │
  │       ↓                                             │
  │  Stable track_id + centroid + velocity assigned     │
  │       ↓                                             │
  │  Vehicles → Async ANPR Queue → EasyOCR worker       │
  │             (background thread, non-blocking)       │
  └─────────────────────────────────────────────────────┘
                        │
                        ▼
  ┌─────────────────────────────────────────────────────┐
  │          STEP 3: AI Enrichment Pipeline              │
  │                                                     │
  │  [A] SuspiciousActivityDetector (per-camera)        │
  │      → obj.attributes["activity"] =                 │
  │          "loitering" | "erratic_movement" |         │
  │          "crowd_formation"                          │
  │       ↓                                             │
  │  [B] VirtualFence (per-camera polygon)              │
  │      → obj.attributes["zone_state"] = "inside"     │
  │      → obj.attributes["zone_id"]  = "border_fence" │
  │       ↓                                             │
  │  [C] FaceRecognitionWorker (async, background)      │
  │      → obj.attributes["identity"] =                 │
  │          "Authorized_Staff" | "Unknown"             │
  └─────────────────────────────────────────────────────┘
                        │
                        ▼ (enriched DetectionResult)
  ┌─────────────────────────────────────────────────────┐
  │          STEP 4: AlarmManager Intelligence Hub       │
  │                                                     │
  │  AlarmManager.submit(result, frame)                 │
  │       │                                             │
  │       ├─→ Score each object via rules.yaml          │
  │       │    Human present       → +20                │
  │       │    Vehicle present     → +25                │
  │       │    Fence breach        → +40                │
  │       │    Loitering           → +35                │
  │       │    Erratic movement    → +30                │
  │       │    Crowd formation     → +35                │
  │       │    ANPR Watchlist hit  → +50                │
  │       │    Total Score → LOW/MEDIUM/HIGH/CRITICAL   │
  │       │                                             │
  │       ├─→ Deduplicate (spatial + temporal)          │
  │       │                                             │
  │       ├─→ Adaptive snapshot capture                 │
  │       │    Score 20–39  → every 2.0s                │
  │       │    Score 40–59  → every 1.0s                │
  │       │    Score 60–79  → every 0.5s                │
  │       │    Score 80+    → every 0.2s (near-video)   │
  │       │                                             │
  │       ├─→ Incident folder created/updated           │
  │       │    storage/incidents/<incident_id>/         │
  │       │      incident.json    (master record)       │
  │       │      snapshot_001.jpg (photo evidence)      │
  │       │      snapshot_002.jpg                       │
  │       │                                             │
  │       ├─→ SQLite WAL Database (events.db)           │
  │       │    activity_log table (every frame)         │
  │       │    events table (every scored event)        │
  │       │                                             │
  │       └─→ WebSocket broadcast → /ws/alerts          │
  │            → All connected dashboard browsers       │
  └─────────────────────────────────────────────────────┘
                        │
                        ▼
  ┌─────────────────────────────────────────────────────┐
  │          STEP 5: Mission Control Dashboard           │
  │         (React 19 + FastAPI + WebSocket)             │
  │                                                     │
  │  Browser: http://localhost:8000/ui                  │
  │  ┌────────────────────────────────────────────┐     │
  │  │ [Live Feed] [Alerts/Incidents] [Detail]    │     │
  │  │  14-cam     WebSocket pushed  Snapshots    │     │
  │  │  MJPEG      Threat meter      PDF export   │     │
  │  │  selector   Radar map         Face ID      │     │
  │  └────────────────────────────────────────────┘     │
  └─────────────────────────────────────────────────────┘
```

---

## 🔬 Module Breakdown

### Module 1 — Human Detection (`human_detection/`)
**Owner:** Prince | **Status:** ✅ Complete & Tested (14 unit tests)

- Uses **YOLOv8n/YOLOv8s** (Ultralytics) to detect human bounding boxes in each camera frame.
- Wrapped in `HumanDetector` class with configurable confidence threshold (`config.yaml`).
- Accepts webcam index, RTSP URL, or MP4 file path via `VideoInputLayer`.
- Outputs: `DetectionResult` with `object_type="human"` + `bbox` + `confidence`.

```python
detector = HumanDetector()
result = detector.detect(frame, camera_id="CAM_01", frame_id=42, timestamp=now)
```

---

### Module 2 — Human Tracking (`human_tracking/`)
**Owner:** Prince | **Status:** ✅ Complete

- Uses **DeepSORT** (appearance + motion tracking) to assign **stable, persistent `track_id`s** across frames (e.g., `h-1`, `h-2`).
- In multi-camera mode, uses a custom **`SimpleIOUTracker`** — a vectorized IOU-based tracker with **per-camera isolated state dictionaries** to prevent cross-camera track contamination (a known issue with ByteTrack).
- Computes **spatial velocity vectors** `(v_x, v_y)` in pixels/second and **centroid history** for behavioral analysis downstream.
- Outputs: Each `DetectedObject` enriched with `attributes["centroid"]` and `attributes["velocity_px_per_s"]`.

---

### Module 3 — Vehicle Detection + ANPR (`vehicle_detection/` + `anpr/`)
**Owner:** Prachi / Mayan | **Status:** ✅ Integrated

- Detects and classifies **cars, motorcycles, buses, and heavy trucks** using YOLOv8n on the same frame.
- **Asynchronous ANPR pipeline**: License plate reading (via EasyOCR) is offloaded to a **dedicated background worker thread** with a bounded FIFO queue (`Queue(maxsize=50)`) to eliminate 300ms stalls on the main video pipeline.
- Plate crops are grayscaled, OCR'd, then regex-cleaned (`[^A-Z0-9]`).
- Plate results are cached against `track_id`s (`veh-X`) and **cross-checked against a local watchlist database** in O(1) time.
- Outputs: `object_type="vehicle"`, `attributes["vehicle_type"]`, `attributes["plate_no"]`, `attributes["watchlist_match"]`.

---

### Module 4 — Virtual Fence / Perimeter Detection (`virtual_fence/`)
**Owner:** Abhilasha | **Status:** ✅ Integrated

- Supports **complex polygonal restricted zones** drawn interactively per camera feed.
- **Calibration Tool** (`roi_calibration.py`): Tactical operators can visually draw fence polygons using click-and-drag in an OpenCV window; coordinates are auto-saved to `{cam_id}_roi.json`.
- **Algorithm**: Uses the **Ray-Casting Point-in-Polygon** test (`cv2.pointPolygonTest`) evaluated at the **bottom-center foot coordinate** `(x_center, y_bottom)` of each tracked object — far more accurate than bounding-box-centroid methods.
- **Selective rendering**: Only alpha-blends warning overlays when a breach is actively detected (`breach_active = True`), saving GPU cycles during normal surveillance.
- Outputs: `attributes["zone_state"] = "inside"`, `attributes["zone_id"] = "border_fence"`.

---

### Module 5 — Suspicious Activity Detection (`suspicious_activity/`)
**Owner:** Omkar | **Status:** ✅ Integrated

- **Loitering Detection**: Flags a person when their centroid remains within a radius of `≤50px` for `≥30 seconds`. Uses a per-`track_id` timer that resets if the person moves.
- **Erratic Movement / Sprinting**: Calculates instantaneous speed from the velocity vector. Flags as `"erratic_movement"` if speed exceeds `3× average walking speed` or exhibits rapid direction reversals.
- **Crowd Formation**: Evaluates pairwise Euclidean distances between all active human tracks on a feed; flags as `"crowd_formation"` when 3+ individuals cluster within a proximity threshold.
- Outputs: `attributes["activity"]` set to `"loitering"` | `"erratic_movement"` | `"crowd_formation"`.

---

### Module 6 — Face Recognition (`face_recognition/`)
**Owner:** Prince | **Status:** ✅ Integrated (async worker)

- Uses **InsightFace (ArcFace + RetinaFace/SCRFD)** for robust face detection and 512-dimensional facial embedding generation.
- **Architecture**: Fully asynchronous — a `FaceRecognitionWorker` background thread processes crops from a `Queue(maxsize=50)`, ensuring **zero FPS drop** on the main pipeline.
- **Persistent identity caching**: Once a `track_id` is matched against the personnel database, the identity is cached for the entire track lifetime. Recognition only needs to succeed **once per person**.
- **FAISS vector search**: Known personnel embeddings are pre-loaded at startup into a FAISS index, enabling sub-2ms matching against thousands of faces.
- **Bypass Rule**: `"Authorized_Staff"` identities are excluded from loitering/crowd/fence scoring, eliminating false alarms on security guards.
- Outputs: `attributes["identity"]` = `"Authorized_Staff"` | `"Unknown"`.

---

### Module 7 — Alarm Manager (`alarm_manager/`)
**Owner:** Prince | **Status:** ✅ Complete

The **central intelligence hub**. All modules call exactly one function:

```python
alarm_manager.submit(result, frame=frame)
```

Internal pipeline:
1. **Score** each object against `rules.yaml` → compute `danger_score` + `danger_label`
2. **Deduplicate** — suppress repeat alerts for the same track within the throttle window
3. **Adaptive snapshot** — crop bbox (+ 15% padding for face quality), JPEG encode via background `ThreadPoolExecutor`
4. **Incident folder** — MD5-hash-based folder per `(camera_id + track_id)`, accumulates all evidence
5. **SQLite WAL write** — logs to `activity_log` and `events` tables with high-throughput WAL mode
6. **WebSocket broadcast** — pushes structured alert JSON to all connected dashboard clients

---

### Module 8 — Website Dashboard (`website/dashboard/`)
**Owner:** Prince | **Status:** ✅ Complete

Built with **React 19 + Vite + Tailwind CSS v4 + Lucide Icons**.

- **3-panel layout**: Live camera feed | Alerts + Incidents center | Detail view
- **14-Camera selector**: Snapshot-based polling (bypasses browser HTTP/1.1 6-connection limit for multi-stream)
- **Threat Radar Map**: Polar-coordinate visualization of active incidents by severity
- **Incident Carousel**: Chronological snapshot strip for each tracked person/vehicle
- **1-Click PDF Export**: Client-side forensic report using `jsPDF`
- **Search & Filter**: By incident ID, camera, activity tag, vehicle type, threat level
- **Personnel Manager**: Manage known staff face database from the UI
- **Auto-reconnect WebSocket** with `localStorage` fallback for last-known data during outages

---

## 📦 The Universal Data Contract

Every single module in IBVAP communicates through **one and only one** shared data structure, defined in `contracts/schema.py`. This is **frozen** — no module can change it without full team sign-off.

```python
# contracts/schema.py

class DetectedObject(BaseModel):
    object_type:  Literal["human", "vehicle"]   # What was detected
    track_id:     str                            # Stable ID: "h-1", "veh-3"
    bbox:         Tuple[int, int, int, int]      # (x1, y1, x2, y2) in pixels
    confidence:   float                          # 0.0 – 1.0
    attributes:   dict                           # Enriched metadata (see below)

class DetectionResult(BaseModel):
    schema_version: str                          # "1.0" — frozen
    module:         VALID_MODULES                # Which module produced this
    camera_id:      str                          # e.g., "CAM_01"
    frame_id:       int                          # Monotonically increasing
    timestamp_utc:  datetime                     # UTC timestamp
    objects:        List[DetectedObject]         # All detected objects
```

### The `attributes` dictionary — How modules talk to each other

| Attribute Key | Set By | Example Value |
|---|---|---|
| `centroid` | HumanTracker | `(320, 240)` |
| `velocity_px_per_s` | HumanTracker | `(12.5, -3.2)` |
| `activity` | SuspiciousDetector | `"loitering"`, `"crowd_formation"`, `"erratic_movement"` |
| `zone_state` | VirtualFence | `"inside"` |
| `zone_id` | VirtualFence | `"border_fence"` |
| `vehicle_type` | VehicleANPR | `"car"`, `"truck"`, `"motorcycle"`, `"bus"` |
| `plate_no` | VehicleANPR | `"DL01AB1234"` |
| `watchlist_match` | ANPR | `True` |
| `identity` | FaceRecognition | `"Authorized_Staff"`, `"Unknown"` |
| `badge_number` | FaceRecognition | `"SSB-2405"` |

> **The Golden Rule:** Every module does exactly **one thing** — enrich the `DetectionResult` and call `alarm_manager.submit(result)`. Nothing else. No alerts, no file saves, no DB writes, no UI calls.

---

## 🎯 Threat Scoring Engine

Threat scoring is **entirely data-driven** — defined in `alarm_manager/configs/rules.yaml`. No code changes are needed to add or modify threat rules.

### Scoring Rules

| Rule | Triggered When | Score | Severity |
|---|---|---|---|
| Human Detected | `module = human_detection` fires | +20 | Informational |
| Human Tracked | `module = human_tracking`, `type = human` | +20 | Informational |
| Vehicle Tracked | `module = human_tracking`, `type = vehicle` | +20 | Informational |
| Vehicle Detected | `module = vehicle_detection` fires | +25 | Informational |
| **Virtual Fence Breach** (Human) | `zone_state = "inside"` | **+40** | High |
| **Virtual Fence Breach** (Vehicle) | `zone_state = "inside"` | **+40** | High |
| **Loitering** | `activity = "loitering"` | **+35** | Medium |
| **Erratic Movement** | `activity = "erratic_movement"` | **+30** | Medium |
| **Crowd Formation** | `activity = "crowd_formation"` | **+35** | Medium |
| **Suspicious Activity** | `module = suspicious_activity` | **+35** | Medium |
| 🚨 **ANPR Watchlist Hit** | `watchlist_match = true` | **+50** | Critical |

### Danger Thresholds

```
Score  0–19  → ⚪ INFORMATIONAL — Logged only, no alert
Score 20–39  → 🟢 LOW           — Logged + low-priority alert
Score 40–59  → 🟡 MEDIUM        — Alert sent, snapshot every 1s
Score 60–79  → 🟠 HIGH          — Alert sent, snapshot every 0.5s
Score 80+    → 🔴 CRITICAL       — Full alert, snapshot every 0.2s (near-video)
```

> Scores are **cumulative** per `track_id`. A person who loiters near a fence and has an unknown identity can reach a score of `20 + 40 + 35 = 95 → CRITICAL`.

---

## 🗄️ Storage & Evidence Management

### Incident Dossier Format

Each unique threat gets an **MD5-hashed incident folder**, meaning the same person/vehicle always accumulates into one record regardless of how many frames they appear in.

```
storage/
└── incidents/
    └── e4b3f1a9d0c2/                 ← Incident ID (MD5 of camera + track_id)
        ├── incident.json             ← Master forensic record
        ├── snapshot_001.jpg          ← Evidence photo 1
        ├── snapshot_002.jpg          ← Evidence photo 2
        └── snapshot_003.jpg          ← Evidence photo 3 (high-threat = many shots)
```

### `incident.json` Schema

```json
{
  "incident_id": "e4b3f1a9d0c2",
  "camera_id": "CAM_01",
  "started_at": "2026-09-20T01:30:00+00:00",
  "last_updated": "2026-09-20T01:30:45+00:00",
  "danger_score": 95,
  "danger_label": "CRITICAL",
  "modules_triggered": ["human_tracking", "virtual_fence", "suspicious_activity"],
  "humans_detected": 2,
  "faces_captured": 1,
  "vehicles_detected": 1,
  "vehicle_types": ["car"],
  "weapons_detected": 0,
  "track_ids": ["h-1", "h-2"],
  "zone_breaches": ["border_fence"],
  "activities_detected": ["loitering"],
  "plate_numbers": ["DL01AB1234"],
  "snapshot_count": 3,
  "snapshots": ["snapshot_001.jpg", "snapshot_002.jpg", "snapshot_003.jpg"],
  "last_snapshot_at": "2026-09-20T01:30:43+00:00"
}
```

### SQLite Database (`storage/events.db`)

Two tables, using WAL mode for non-blocking concurrent writes:

| Table | Purpose |
|---|---|
| `activity_log` | Every single frame detection (all objects, all modules, timestamp) |
| `events` | Only events where a scoring rule triggered (incident-level) |

---

## 📡 Mission Control Dashboard

Access at **`http://localhost:8000/ui`** after starting the server.

### 3-Panel Layout

```
┌──────────────────┬───────────────────────────────┬──────────────────┐
│  Camera Panel    │     Monitor Panel              │  Detail Panel    │
│                  │                                │                  │
│  Live MJPEG feed │  [Alerts Tab] [Incidents Tab]  │  Snapshot gallery│
│  14-cam selector │  Live WebSocket alerts stream  │  Threat meter    │
│  Threat HUD      │  Radar map (polar coords)      │  Timeline        │
│  Human count     │  Search & filter               │  PDF export btn  │
└──────────────────┴───────────────────────────────┴──────────────────┘
```

### Dashboard Features

| Feature | Description |
|---|---|
| 🎥 Live Feed | MJPEG stream — `<img src="/stream/live">` — no plugin needed |
| 📷 14-Camera Grid | Snapshot-polling matrix (bypasses Chrome's 6-connection limit) |
| 🔴 Live Alert Feed | Auto-animates on new WebSocket push — color coded by severity |
| 📁 Incidents Tab | Folder-based cards with snapshot gallery + metadata |
| 🎯 Radar Map | Real-time polar threat map of active incidents |
| 🔍 Search | Search by incident ID, camera, activity tag, vehicle type |
| 🔽 Filter | Filter by Humans / Vehicles / High Threat / Watchlist |
| 📄 PDF Report | Client-side `jsPDF` — instant court-ready forensic PDF |
| 👤 Personnel Mgr | Add/remove authorized staff from the UI (with photo upload) |
| ♻️ Auto-Reconnect | WebSocket with `localStorage` fallback for offline resilience |

---

## 🌐 REST API & WebSocket Reference

The **FastAPI** server (`alarm_manager/src/api.py`) exposes:

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Health check — returns version + dashboard URL |
| `/ui` | GET | Serves the React 19 dashboard (built static files) |
| `/docs` | GET | Interactive Swagger API documentation |
| `/stream/live` | GET | MJPEG grid stream of all cameras |
| `/stream/camera/{cam_id}` | GET | Individual camera MJPEG stream |
| `/stream/snapshot/{cam_id}` | GET | Latest JPEG snapshot of a specific camera |
| `/api/cameras` | GET | List all registered cameras + live status |
| `/api/cameras/{cam_id}/select` | POST | Switch which camera receives full AI processing |
| `/api/cameras/{cam_id}/fence` | GET/POST | Read or update the virtual fence polygon for a camera |
| `/api/live` | GET | Per-frame live telemetry (human count, FPS) |
| `/api/stats` | GET | Aggregate stats for dashboard stat cards |
| `/api/events` | GET | Recent events from SQLite (paginated, `?limit=50`) |
| `/api/incidents` | GET | All incident dossiers (`?limit=30`) |
| `/api/incidents/{id}` | GET | Single incident detail JSON |
| `/storage/incidents/{id}/{file}` | GET | Direct access to snapshot images |
| `/ws/alerts` | WebSocket | Real-time push of every new alert to connected browsers |

---

## ⚡ Performance Benchmarks

Tested on **NVIDIA RTX 3050 Laptop GPU (4GB VRAM)**:

| Optimization Stage | Latency | FPS | Improvement |
|---|---|---|---|
| Baseline (PyTorch FP32 CPU) | ~110ms | 9.1 FPS | 1.0× |
| Torch CUDA FP16 | ~45ms | 22.2 FPS | 2.4× |
| **TensorRT FP16 Engine** | **~9.4ms** | **33.7 FPS** | **3.7×** |
| + Async ANPR Offloading | Stalls removed | — | Eliminates 300ms spikes |
| + Threaded JPEG Encoding | Saved 60ms/frame | — | Pipeline never blocks |

### Key Engineering Optimizations

1. **TensorRT FP16 Graph Fusion** — Converts YOLO weights to `.engine` files with layer fusion and half-precision math
2. **Per-Camera IOU Tracking** — Custom `SimpleIOUTracker` eliminates DeepSORT/ByteTrack cross-camera contamination
3. **Vectorized IOU Matrix** — `NumPy` batch operations for bounding box matching (`<1.0ms` per camera)
4. **SQLite WAL Mode** — `PRAGMA journal_mode=WAL` + 64MB page cache for non-blocking concurrent writes
5. **Async ANPR Queue** — EasyOCR runs in a `Thread` + `Queue(maxsize=50)` — zero main-loop stall
6. **ThreadPoolExecutor JPEG Encoding** — `cv2.imencode` offloaded from main thread (saves 60–80ms/frame)
7. **Zero-Copy Frame Ring Buffers** — Lock-guarded circular references prevent array copies across threads

---

## 🚀 How to Run the Project

### Prerequisites

- **OS**: Windows 10/11 or Ubuntu 20.04+ (Windows recommended for TensorRT)
- **Python**: 3.10 or 3.12
- **GPU**: NVIDIA GPU with CUDA 11.8+ (CPU fallback available, slower)
- **RAM**: 8GB minimum, 16GB recommended
- **Webcam / RTSP Camera** or an MP4 video file for testing

---

### Step 1 — Clone the Repository

```bash
git clone https://github.com/Geet-Prince/ibvap.git
cd ibvap
```

---

### Step 2 — Install Python Dependencies

```bash
pip install -r requirements.txt
```

> For DeepSORT tracking (used in `run_live.py`):
```bash
pip install deep-sort-realtime
```

> For ANPR (if not auto-installed):
```bash
pip install easyocr
```

> For Face Recognition (if not auto-installed):
```bash
pip install insightface faiss-cpu onnxruntime
```

---

### Step 3 — (Optional) Build the Dashboard

> **Skip this step** if the `website/dashboard/dist/` folder already exists — the built UI is ready to serve.

If you need to rebuild:
```bash
cd website/dashboard
npm install
npm run build
cd ../..
```

---

### Step 4 — Verify the System (Recommended Before Demo)

Run the system audit to confirm all 13 checks pass:

```bash
python system_audit.py
```

Expected output:
```
✅  13/13 checks passed — System is ready to run.
```

---

### Step 5 — Run Everything (Single Command)

```bash
# Default: uses webcam (camera index 0)
python run_ibvap.py
```

```bash
# Use a video file instead of webcam
python run_ibvap.py --source path/to/video.mp4
```

```bash
# Use an RTSP camera
python run_ibvap.py --source rtsp://192.168.1.100:554/stream
```

This single command:
1. Starts the **FastAPI server** on port `8000`
2. Launches all camera capture threads
3. Starts the **AI inference pipeline** (YOLO → Track → ANPR → Behavior → Fence → Face)
4. Starts the **AlarmManager** (scoring → snapshots → DB → WebSocket)

---

### Step 6 — Open the Dashboard

Open your browser and go to:

```
http://localhost:8000/ui
```

You should see the live Mission Control dashboard with the camera feed, alert stream, and incident list.

---

### Alternative: Split-Terminal Mode (for development)

```bash
# Terminal 1 — Start the FastAPI server
python start_server.py

# Terminal 2 — Run the AI pipeline
python run_live.py
# or with a video file:
python run_live.py --source path/to/video.mp4
```

---

### Step 7 — Calibrate Virtual Fence Polygons (Optional)

If you want to define restricted zones for your specific camera angles:

```bash
# Interactive visual fence calibration tool
python virtual_fence/roi_calibration.py --camera 0
```

- Click to add polygon vertices
- Press `s` to save
- Coordinates are saved to `virtual_fence/{camera_name}_roi.json`

---

### Running Contract Tests (for developers)

```bash
pytest tests/contract/ -v
```

These tests verify all modules conform to the `DetectionResult` schema. They **must pass before any code merge**.

---

### Keyboard Controls (Live Window)

| Key | Action |
|---|---|
| `q` | Stop the pipeline and exit |

---

## 📁 Project Structure

```
ibvap/
│
├── run_ibvap.py              ← 🚀 SINGLE ENTRY POINT — run this to start everything
├── run_live.py               ← Alternative: detection-only (no multi-camera)
├── start_server.py           ← Alternative: start FastAPI server separately
├── system_audit.py           ← Verifies all 13 system checks pass
├── requirements.txt          ← All Python dependencies
│
├── contracts/                ← 🔒 FROZEN shared schema — never modify without sign-off
│   ├── schema.py             ← DetectionResult + DetectedObject (Pydantic v2)
│   ├── fake_detector.py      ← FakeDetector for parallel dev without real models
│   └── __init__.py
│
├── human_detection/          ← Module 1: YOLOv8 human detection (Prince)
│   ├── inference/
│   │   ├── detector.py       ← HumanDetector class
│   │   └── video_input.py    ← VideoInputLayer (RTSP/webcam/file)
│   ├── configs/config.yaml   ← Confidence threshold, model path, etc.
│   └── testing/              ← 14 unit tests
│
├── human_tracking/           ← Module 2: DeepSORT tracking (Prince)
│   ├── inference/
│   │   └── tracker.py        ← HumanTracker class
│   ├── configs/config.yaml
│   └── testing/
│
├── vehicle_detection/        ← Module 3: YOLOv8 vehicle + ANPR (Prachi/Mayan)
│   └── inference/
│       └── vehicle_anpr.py   ← VehicleANPR class (async plate reading)
│
├── anpr/                     ← ANPR sub-module
│   └── plate_reader.py       ← PlateReader (EasyOCR + watchlist)
│
├── virtual_fence/            ← Module 4: Polygon perimeter detection (Abhilasha)
│   ├── fence_detector.py     ← VirtualFence class (ray-casting PiP)
│   ├── roi_calibration.py    ← Interactive fence drawing tool
│   ├── roi_config.json       ← Default saved fence coordinates
│   └── {cam_id}_roi.json     ← Per-camera fence coordinates
│
├── suspicious_activity/      ← Module 5: Behavioral AI (Omkar)
│   ├── loitering_detector.py ← SuspiciousActivityDetector class
│   └── testing/
│
├── face_recognition/         ← Module 6: InsightFace ArcFace recognition (Prince)
│   ├── core.py               ← FaceRecognitionWorker (async background thread)
│   └── router.py             ← FastAPI routes for personnel management
│
├── alarm_manager/            ← Module 7: Intelligence hub (Prince)
│   ├── configs/
│   │   └── rules.yaml        ← 🎯 Threat scoring rules (edit freely)
│   └── src/
│       ├── core.py           ← AlarmManager.submit() — main scoring engine
│       ├── api.py            ← FastAPI app (REST + WebSocket + MJPEG)
│       ├── incident_store.py ← Writes incident.json + snapshots
│       ├── database.py       ← SQLite WAL setup + read/write
│       └── frame_buffer.py   ← Thread-safe FrameBuffer + CameraRegistry
│
├── website/                  ← Module 8: React dashboard (Prince)
│   └── dashboard/
│       ├── src/
│       │   ├── App.jsx
│       │   ├── components/dashboard/
│       │   │   ├── DashboardLayout.jsx   ← Main layout (3-panel)
│       │   │   ├── CameraPanel.jsx       ← Live feed + camera selector
│       │   │   ├── MonitorPanel.jsx      ← Alerts + Incidents tabs
│       │   │   ├── DetailPanel.jsx       ← Selected incident detail
│       │   │   ├── AlertList.jsx         ← WebSocket alert stream
│       │   │   ├── TopBar.jsx            ← Header + connection status
│       │   │   ├── StatStrip.jsx         ← Stat cards (humans/vehicles/etc.)
│       │   │   ├── RadarMap.jsx          ← Polar threat radar
│       │   │   ├── PersonnelManager.jsx  ← Staff face database UI
│       │   │   └── ...
│       │   ├── hooks/
│       │   │   └── useLiveAlerts.js      ← WebSocket auto-reconnect hook
│       │   └── lib/
│       │       ├── api.js                ← REST API client
│       │       ├── pdfReport.js          ← jsPDF forensic report generator
│       │       └── config.js             ← Base URL config
│       ├── package.json
│       └── vite.config.js
│
├── configs/
│   ├── system.yaml           ← Camera definitions, model states, timing
│   └── rules.yaml            ← System-level alarm rules
│
├── storage/                  ← Auto-created at runtime (do not commit)
│   ├── events.db             ← SQLite database
│   └── incidents/
│       └── {incident_id}/
│           ├── incident.json
│           └── snapshot_XXX.jpg
│
├── tests/
│   ├── contract/             ← CI gate tests (must pass on every PR)
│   └── fixtures/scenarios/   ← Shared test data for all modules
│
├── docs/
│   ├── DATA_FLOW.md          ← Detailed data flow reference
│   ├── AI_BUILD_BRIEF.md     ← Instructions for AI coding assistants
│   └── TEAM_INTEGRATION_BRIEF.md
│
├── yolov8n.pt                ← YOLOv8 nano weights (CPU/small GPU)
└── yolov8s.engine            ← YOLOv8s TensorRT FP16 engine (fast GPU)
```

---

## 🛠️ Technology Stack

| Layer | Technology | Version | Why We Chose It |
|---|---|---|---|
| Core AI & Vision | Ultralytics YOLOv8 | YOLOv8s / YOLOv8n | Best mAP vs inference speed balance for real-time multi-class detection |
| Inference Acceleration | NVIDIA TensorRT | TensorRT 10.x (FP16) | Hardware kernel fusion — 3–5× faster than standard PyTorch CUDA |
| Object Tracking | SimpleIOUTracker / DeepSORT | Custom / deep-sort-realtime | Per-camera isolation avoids cross-camera ID contamination |
| Face Recognition | InsightFace (ArcFace) | onnxruntime GPU | Robust at angles, low light, and distance; 512D embeddings |
| Vector Search | FAISS | faiss-cpu | Sub-2ms face matching against thousands of known personnel |
| OCR / ANPR | EasyOCR | PyTorch GPU | High accuracy on skewed, low-resolution, dirty license plates |
| Backend API | FastAPI + Uvicorn | Python 3.12 (ASGI) | Native async WebSocket + high-speed REST in one framework |
| Data Contract | Pydantic v2 | Pydantic Core | Runtime type enforcement across all modules without tight coupling |
| Edge Database | SQLite 3 | WAL Mode | Zero-maintenance embedded DB; handles 100k+ records/day with WAL |
| Image Processing | OpenCV | opencv-contrib | BGR transforms, ROI polygon math, JPEG encode |
| Frontend | React | React 19 + Vite 8 | Component-driven reactive UI with sub-second hot builds |
| Styling | Tailwind CSS + Lucide | Tailwind v4 | Military dark-theme tactical UI, fully responsive |
| PDF Export | jsPDF | v4.x | Client-side vector PDF — no server load, instant export |
| Testing | pytest + pytest-asyncio | 8.x | Contract tests gate every PR |
| Code Quality | Black + Ruff + pre-commit | Latest | Enforces consistent style across all team members |

---

## 💰 Feasibility & Economics

### Technical Feasibility ⭐⭐⭐⭐⭐
- Compatible with **standard ONVIF/RTSP IP cameras**, USB webcams, thermal cameras, and MP4 files
- Proven to run **14+ simultaneous streams at 30+ FPS** on NVIDIA RTX 3050 (4GB VRAM, ~₹40,000)
- Full **CPU fallback mode** available (PyTorch FP32) for deployment without GPU

### Economic Feasibility ⭐⭐⭐⭐⭐

| Solution | Cost per Border Outpost |
|---|---|
| Traditional Proprietary VMS (e.g., Milestone, Genetec) | ₹15,00,000 – ₹40,00,000 |
| **IBVAP on COTS Edge GPU PC** | **₹80,000 – ₹1,50,000** |
| **IBVAP on Existing SSB Hardware** | **₹0 (software only)** |

> **90%+ cost reduction** with zero licensing fees — 100% open source stack.

### Operational Feasibility ⭐⭐⭐⭐⭐
- **30-second fence calibration**: Operators draw polygonal zones with a click-and-drag visual tool
- **Offline-first**: Zero cloud dependency — operates continuously even if satellite links are severed
- **Single command startup**: `python run_ibvap.py` — no DevOps expertise required

---

## 🔧 Key Engineering Challenges Solved

| Challenge | Root Cause | How We Solved It |
|---|---|---|
| Pipeline freeze during ANPR | EasyOCR takes 300ms+ inline on main loop | Decoupled ANPR into background thread + bounded queue |
| Cross-camera track contamination | ByteTrack merges tracks across different feeds | Custom `SimpleIOUTracker` with per-camera state dictionaries |
| Browser freeze with 14 streams | HTTP/1.1 max 6 connections per domain (Chrome/Edge) | Replaced MJPEG streams with auto-refreshing snapshot polling matrix |
| SQLite lock contention | Concurrent AI loop writes locked the DB file | SQLite WAL mode + thread-safe batched write queues |
| CPU render stalls | `cv2.imencode(".jpg")` took 65–80ms per frame | Offloaded JPEG compression to `ThreadPoolExecutor` workers |
| JSON serialization crashes | NumPy `int64`/`float32` types broke JSON exports | Explicit native type casting `tuple(map(int, bbox))` across all trackers |
| False alarms on security guards | Guards naturally trigger loitering + fence rules | Face recognition worker identifies staff and bypasses behavioral scoring |

---

## 🗺️ Future Roadmap

| Phase | Feature | Description |
|---|---|---|
| Phase 2 | Thermal / IR Integration | Direct support for LWIR cameras — zero-visibility night surveillance |
| Phase 2 | Hash-Chain Tamper Evidence | Cryptographic chain-of-custody on the SQLite `events` table |
| Phase 2 | Edge-to-HQ Mesh Sync | Peer-to-peer sync between outposts and central command over low-bandwidth tactical radio |
| Phase 3 | Drone / UAV Feed Telemetry | Dynamic polygon fencing for moving aerial camera coordinates |
| Phase 3 | Continuous 30s Video Buffer | Rolling video clip storage for pre-incident footage replay |

---

## 👥 Team

> **Smart India Hackathon 2026** | Problem Statement: SSB Border Surveillance Analytics

| Member | Role | Modules |
|---|---|---|
| **Prince Raj** | Architecture & AI Core Lead | Human Detection, Human Tracking, Alarm Manager, Face Recognition, Dashboard, System Integration |
| **Abhilasha Jha** | Perimeter Security | Virtual Fence Intrusion Detection, ROI Calibration Tool |
| **Omkar Mishra** | Behavioral AI | Suspicious Activity Detection (Loitering, Erratic, Crowd) |
| **Prachi / Mayan** | Vehicle Intelligence | Vehicle Detection + Classification, ANPR Plate Reading |

**GitHub:** [Geet-Prince/ibvap](https://github.com/Geet-Prince/ibvap)  
**Lead Contact:** Prince Raj — prince.raj.ds@gmail.com

---

<div align="center">

**Built for Smart India Hackathon 2026 🇮🇳**  
*Protecting India's borders with open-source AI*

</div>
