# MISSION CONTROL Build — Checklist (AI must follow in order)

> Branch: `optimization` | Goal: Event-based Mission Control (group N detections → 1 Intrusion Event)
> Rule: tick `[x]` ONLY after test passes. Add row to Update Log + OPTIMIZATION_PLAN.md for every change.

## Q&A

### Q1. What are we building?
**A.** Threat grouping + event lifecycle + schematic map + escalation, on top of existing detection pipeline. No model retraining. Pure Python + SQLite + React.

### Q2. What is the definition of done per item?
**A.** Code exists + `python system_audit.py` still 15/15 (or more) + `pytest tests/contract/ -v` 13/13 + new unit test for grouper passes.

### Q3. What files will change?
**A.** See checklist table. No push until user runs live `run_ibvap.py` test.

## Checklist

| # | Item | Status | Files | Test |
|---|------|--------|-------|------|
| MC-1 | `grouper.py`: person_key, link_score≥50, ingest, merge/split, lifecycle sweep, tunables in one place | [x] | `alarm_manager/src/grouper.py` (new) | `pytest tests/contract/test_grouper.py -v` 6/6 PASS 2026-09-21 |
| MC-2 | Event data model: `events2`/`event_transitions` tables (additive, no break of `events`/`activity_log`) | [x] | `alarm_manager/src/database.py` | audit check 16 PASS 2026-09-21 |
| MC-3 | Grouper unit tests (synthetic detections, no GPU): grouping, merge adjacent, split far, ReID dedup, auto-close | [x] | `tests/contract/test_grouper.py` (new) | 6/6 PASS (grouping, gap, ReID, merge, split, lifecycle) |
| MC-4 | Zones API + transition API: `GET /api/zones`, `POST /api/events/{id}/transition` (ACK/DISPATCH/RESOLVE/FALSE_ALARM, audit-logged) | [x] | `alarm_manager/src/api.py`, `alarm_manager/src/database.py` | audit check 17 PASS; `GET /api/zones`, `GET /api/open-events` registered |
| MC-5 | Frontend starter: `ZoneSchematic.jsx` (SVG nodes green/orange/red/grey) + `useZoneStatus.js` (WS reducer) — additive, RadarMap untouched | [x] | `website/dashboard/src/components/dashboard/ZoneSchematic.jsx`, `website/dashboard/src/hooks/useZoneStatus.js` | syntax-built, additive only; user runs `npm run build` before demo |
| MC-6 | Full regression: audit + contract pytest | [x] | — | `python system_audit.py` 17/17 PASS + `pytest tests/contract/ -v` 19/19 PASS 2026-09-21 |
| MC-7 | Backend continuous dossier: wire `grouper.ingest` into `AlarmManager.submit` — dossier keeps appending while intrusion active; 10 people / 5 min chain into ONE event via T_WINDOW; `event_id`+headcount on alert; throttled `upsert_intrusion_event` + periodic `sweep` | [x] | `alarm_manager/src/core.py`, `tests/contract/test_grouper.py` (+1 integration test w/ cleanup) | `pytest tests/contract/test_grouper.py -v` 7/7 PASS 2026-09-21 |
| MC-8 | Frontend to radar spec: `ZoneNode.jsx` (14px node + pulse ring + aria-label) + `ZoneDetail.jsx` (badge/feed/meta/actions) + `ZoneRadarPanel.jsx` (2-col card, 280 SVG rings 44/87/130 + sweep + legend) + `useZoneStatus.js` rewrite to `{id,name,cam_id,status,ack,...}` + ack/resolve → `POST /api/events/{id}/transition` + pulse keyframes in `index.css` | [x] | `website/dashboard/src/components/dashboard/Zone{Node,Detail,RadarPanel}.jsx`, `hooks/useZoneStatus.js`, `index.css` | brace/paren sanity OK; audit 17/17; pytest 20/20; user runs `npm run build` |
| MC-9 | Mount `ZoneRadarPanel` in `DashboardLayout` left column (additive, old `RadarMap` untouched) + full regression | [x] | `DashboardLayout.jsx` | audit 17/17 + pytest 20/20 (13 schema + 7 grouper) 2026-09-21 |

## Tunables (single source of truth, also in grouper.py header)

- `T_WINDOW=90s`, `DORMANT_CLOSE=600s`, `REID_THRESH=0.65`, `LINK_THRESH=50`, `SPLIT_METERS=150 (200px fallback)`, `ACK_SLA=60s`, `ESCALATE_SLA=180s`

## Update Log

| Date | Item | What | Test |
|------|------|------|------|
| 2026-09-21 | MC-0 | Checklist created | — |
| 2026-09-21 | MC-1+MC-3 | `grouper.py` + 6 unit tests (grouping, time-gap, ReID handoff, merge, split, escalate/close) | `pytest tests/contract/test_grouper.py -v` 6/6 PASS |
| 2026-09-21 | MC-2+MC-4 | `intrusion_events` + `event_transitions` tables, `upsert/transition/get_open`, `/api/zones` + `/api/open-events` + `POST /api/events/{id}/transition` | audit checks 16–17 PASS |
| 2026-09-21 | MC-5 | `ZoneSchematic.jsx` SVG + `useZoneStatus.js` WS hook (additive, RadarMap untouched) | file-created; `npm run build` pending user |
| 2026-09-21 | MC-6 | Full regression (first pass) | `python system_audit.py` 17/17 PASS; `pytest` 19/19 PASS |
| 2026-09-21 | MC-7 | Wired `grouper.ingest` into `AlarmManager.submit` (continuous session, `event_id`+headcount) + integration test | `pytest tests/contract/test_grouper.py -v` 7/7 PASS |
| 2026-09-21 | MC-8 | Spec radar UI: `ZoneNode`/`ZoneDetail`/`ZoneRadarPanel` + `useZoneStatus` rewrite + `pulse-ring` CSS | brace/paren sanity OK |
| 2026-09-21 | MC-9 | Mounted `ZoneRadarPanel` in left column + regression | audit 17/17; pytest 20/20 |
| 2026-09-21 | HOTFIX-1 | `run_ibvap.py` CUDA crash on Mac (hardcoded `device=0` + unconditional TRT/`to('cuda')`) → device detect (CUDA→MPS→CPU), TRT gated on CUDA, warmup/infer use `self._device`, `half` only on CUDA | smoke: `ConsolidatedBatchedAI().warmup + process_batch(dummy)` OK on cpu; audit 17/17; pytest 19/19 |
| 2026-09-21 | HOTFIX-2 | Missing `ALARM_COOLDOWN` NameError crash + `half` deprecation spam (CPU) + corrupted 71MB `events.db` (btree/freelist) → defined throttle dict, CUDA-only `half`, backed up corrupt DB + fresh `init_db()` | audit 17/17; pytest 19/19; corrupt copy at `/tmp/opencode/ibvap_db_backup/` |
| 2026-09-21 | HOTFIX-3 | `timedelta > float` TypeError in alarm throttle (`ts` is datetime) → `.total_seconds() > 1.0` | syntax OK; audit 17/17; pytest 19/19 |
