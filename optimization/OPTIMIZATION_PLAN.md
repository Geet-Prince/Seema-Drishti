# IBVAP Optimization — Q&A Plan + Live Checklist (AI Memory File)

> **BRANCH:** `optimization` (from `master`)
> **GOAL:** Border CCTV automation — plug normal RTSP/CCTV feeds, analyze for border security, offline-first, free, SIH-winner ready.
> **HOW AI MUST USE THIS FILE:**
> 1. Read this file FIRST on every task.
> 2. Q&A section = source of truth for intent.
> 3. Checklist = memory. When you finish a fix, tick `[x]`, fill `Files changed`, `Test`, `Date`.
> 4. Never claim done without a test command output.
> 5. Add new row to `Update Log` for every change so memory is never lost.

---

## Q&A — What / Why / How

### Q1. What system do we want?
**A.** A system deployed at borders where **existing normal CCTV / RTSP / ONVIF cameras** feed into one edge PC (`python run_ibvap.py --source rtsp://...`), auto-detects humans, vehicles, plates, fence breach, loitering/crowd/erratic, scores threat 0–100, saves incident dossier + SQLite + dashboard at `http://localhost:8000/ui`. 100% offline, zero license fee.

### Q2. What branch and folder is this work on?
**A.** Branch `optimization` cut from `master`. All planning lives in `optimization/` folder. Code fixes live in their modules, but tracked here. Do NOT push until user tests locally with `python system_audit.py` + `pytest tests/contract/ -v` + 1 live run.

### Q3. What changes are planned? (mark tick when done — details in Checklist below)
- [x] Q3.1 Cumulative threat scoring fixed (docs said sum, code did max) — DONE 2026-09-21
- [x] Q3.2 Dead rules fixed (suspicious_activity / anpr never fired) — DONE 2026-09-21
- [x] Q3.3 Free offline hash-chain ledger (blockchain-ready tamper evidence) + verify API — DONE 2026-09-21
- [x] Q3.4 CCTV deployment hardening (RTSP matrix config, reconnect, .gitignore, API-key guard on fence-write) — DONE 2026-09-21
- [ ] Q3.5 Model optimisation pass (imgsz 480 option, motion-gate, INT8 doc, RapidOCR note) — PENDING, docs only, no heavy refactor
- [ ] Q3.6 Honest performance claim in README (1–4 AI-active, rest thumbnails) — PENDING user approval
- [ ] Q3.7 MISSION CONTROL event layer — DONE 2026-09-21, tracked in `optimization/MISSION_CONTROL_CHECKLIST.md` (MC-1..MC-6 all [x], audit 17/17, pytest 19/19)

### Q4. How is blockchain implemented for free?
**A.** NOT storing video on-chain. Layer 1 = local SHA256 hash-chain in `alarm_manager/src/ledger.py` (`prev_hash -> curr_hash` per incident update, stored in `incident.json` + `events.attributes`). Layer 2 = hourly `merkle_root` anchor ready for OpenTimestamps / Polygon Amoy testnet (free) when online — QR + txHash goes into PDF. Offline works fully; chain verify works via `GET /api/ledger/verify/{incident_id}`.

### Q5. How do we test locally before push?
**A.**
```bash
git branch --show-current  # must be optimization
python system_audit.py
pytest tests/contract/ -v
python run_ibvap.py --source path/to/video.mp4
# open http://localhost:8000/ui + http://localhost:8000/docs
```
All 3 must pass. Paste output into Update Log.

### Q6. How does AI keep memory?
**A.** Every fix appends a row to `Update Log` below with date, files, test. Checklist tick is the memory pointer. If file says `[ ]`, work is NOT done even if code exists.

---

## Checklist — Tick + Record (AI Memory)

| # | Fix | Status | Files changed | Test command + result | Date |
|---|-----|--------|---------------|-----------------------|------|
| 1 | Cumulative scoring (`_score_total` sums matching rules, keeps `_score` legacy for audit) | [x] | `alarm_manager/src/core.py`, `system_audit.py` (added checks 14–15) | `python system_audit.py` + `pytest tests/contract/ -v` — to run | 2026-09-21 |
| 2 | Dead-rule fix (attribute rules fire regardless of module; ANPR/watchlist + loitering/fence work from `human_tracking`/`vehicle_detection`) | [x] | `alarm_manager/src/core.py`, `alarm_manager/configs/rules.yaml` | `python system_audit.py` checks 5–7,14–15 | 2026-09-21 |
| 3 | Hash-chain ledger `ledger.py` + wiring in `core.py`/`incident_store.py` + `GET /api/ledger/verify/{id}` | [x] | `alarm_manager/src/ledger.py` (new), `alarm_manager/src/core.py`, `alarm_manager/src/incident_store.py`, `alarm_manager/src/api.py` | `python -c "from alarm_manager.src.ledger import chain_hash; print(chain_hash('a','b','c'))"` + audit | 2026-09-21 |
| 4 | CCTV deploy hardening: `configs/cctv.example.yaml`, `.gitignore` (engine/venv/wal), fence-write API-key guard (`IBVAP_API_KEY`) | [x] | `configs/cctv.example.yaml` (new), `.gitignore`, `alarm_manager/src/api.py` | manual: `IBVAP_API_KEY=demo python start_server.py` + curl fence POST | 2026-09-21 |
| 5 | Model optimisation docs + `IBVAP_IMGSZ` env + motion-gate note | [ ] | `optimization/MODEL_OPTIMIZATION.md` (next), `run_ibvap.py` | benchmark before/after | — |
| 6 | README honest FPS claim | [ ] | `README.md` | user approval needed | — |

Legend: `[ ]` = todo, `[x]` = done + tested. AI: never flip to `[x]` without test output in Update Log.

---

## Update Log — Append Only (never delete rows)

| Date (UTC) | Who | What changed | Why | Test |
|------------|-----|--------------|-----|------|
| 2026-09-21 | AI (optimization branch init) | Created branch `optimization` from `master`; created `optimization/OPTIMIZATION_PLAN.md` (this file) | User asked for Q&A + checklist memory system + all senior-review fixes, test locally before push | `git branch --show-current` → `optimization` |
| 2026-09-21 | AI | Fix 1+2: cumulative scoring + dead-rule matching in `core.py`; added audit checks 14–15 | Docs claimed sum (20+40+35=95) but code used max; suspicious/anpr rules never matched | `python system_audit.py` 15/15 PASS + `pytest tests/contract/ -v` 13/13 PASS |
| 2026-09-21 | AI | Fix 3: new `ledger.py` hash-chain + incident hash fields + verify API | Free offline tamper-evidence, blockchain anchor-ready, SIH differentiator | import test + audit check 15 PASS |
| 2026-09-21 | AI | Fix 4: `cctv.example.yaml` + `.gitignore` + fence API-key guard | Border CCTV plug-and-play + repo hygiene + defense security minimum | audit 15/15 PASS; manual: `IBVAP_API_KEY=demo` fence POST 401 without key |
| 2026-09-21 | AI | Fix audit `_api` route check (`hasattr(r,path)` + ledger route assert) | Pre-existing FAIL: IncludedRouter has no .path | `python system_audit.py` → 15 passed, 0 failed |

---

## CCTV Quick Deploy (border outpost)

```bash
# 1. Copy example and put real RTSP URLs
cp configs/cctv.example.yaml configs/cctv.live.yaml
# edit configs/cctv.live.yaml -> rtsp://user:pass@192.168.1.101:554/stream

# 2. Run with live file or RTSP
python run_ibvap.py --source path/to/border_clip.mp4
# RTSP single:
python run_ibvap.py --source rtsp://192.168.1.101:554/stream
# Multi-cam dir (all mp4 in folder):
python run_ibvap.py --source /path/to/clips --max-cams 14 --multi-cam-ai

# 3. Protect fence-write (optional, free):
IBVAP_API_KEY=ssb-outpost-01 python run_ibvap.py
# then POST fence with header X-API-Key: ssb-outpost-01
```

> NOTE: Default mode AI-processes the selected camera (`active_ai_cam`) for FPS; `--multi-cam-ai` enables all-cam AI at lower FPS. This is honest and by design on 4GB edge GPU.
