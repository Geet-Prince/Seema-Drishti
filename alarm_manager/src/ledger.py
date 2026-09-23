"""
alarm_manager/src/ledger.py — Free offline hash-chain (blockchain-ready tamper evidence)
Owner: optimization branch

Design (Rs.0, offline-first):
  curr_hash = SHA256(prev_hash + "|" + incident_id + "|" + str(score) + "|" + timestamp + "|" + snapshot_hash + "|" + attrs_hash)
Genesis prev_hash = "GENESIS".

- No deps, stdlib only.
- Stored in incident.json under meta["ledger"] = {prev_hash, curr_hash, updated_at, event_count}.
- events.attributes also carries ledger_hash for DB-level verification.
- Layer 2 anchor (when online): merkle_root(hashes) -> OpenTimestamps / Polygon Amoy testnet (free).
  See merkle_root() + build_anchor_payload(). No network calls here by design (offline).
"""
from __future__ import annotations

import hashlib
import json
from typing import Iterable

GENESIS = "GENESIS"


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def chain_hash(prev_hash: str, incident_id: str, score: int, timestamp: str,
               snapshot_hash: str = "", attributes: dict | None = None) -> str:
    attrs_hash = _sha256_hex(json.dumps(attributes or {}, sort_keys=True, separators=(",", ":")))
    payload = "|".join([prev_hash or GENESIS, incident_id, str(score), timestamp or "", snapshot_hash or "", attrs_hash])
    return _sha256_hex(payload)


def next_entry(prev_hash: str, incident_id: str, score: int, timestamp: str,
               snapshot_hash: str = "", attributes: dict | None = None) -> dict:
    prev = prev_hash or GENESIS
    curr = chain_hash(prev, incident_id, score, timestamp, snapshot_hash, attributes)
    return {"prev_hash": prev, "curr_hash": curr}


def merkle_root(hashes: Iterable[str]) -> str:
    """Free anchor helper: pairwise SHA256 up the tree. Returns '' for empty."""
    level = [h for h in hashes if h]
    if not level:
        return ""
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            a = level[i]
            b = level[i + 1] if i + 1 < len(level) else a
            nxt.append(_sha256_hex(a + b))
        level = nxt
    return level[0]


def build_anchor_payload(incident_ids: list[str], curr_hashes: list[str]) -> dict:
    """Payload to anchor when online (OpenTimestamps / Polygon testnet). No network here."""
    root = merkle_root(curr_hashes)
    return {
        "protocol": "ibvap-ledger-v1",
        "merkle_root": root,
        "count": len(curr_hashes),
        "incidents": incident_ids,
        "verify_hint": "recompute chain_hash per incident, then merkle_root, compare to anchored root",
    }


def verify_incident_chain(meta: dict) -> dict:
    """Best-effort local verify. incident.json stores only latest link;
    full history verify needs events table scan (done in api endpoint)."""
    ledger = (meta or {}).get("ledger") or {}
    if not ledger.get("curr_hash"):
        return {"valid": False, "reason": "no ledger hash yet (incident too new or pre-ledger)"}
    # Structural check only here; cryptographic re-walk happens in api using DB rows.
    if len(ledger["curr_hash"]) != 64 or (ledger.get("prev_hash") and len(ledger["prev_hash"]) != 64 and ledger["prev_hash"] != GENESIS):
        return {"valid": False, "reason": "malformed hash"}
    return {"valid": True, "curr_hash": ledger["curr_hash"], "prev_hash": ledger.get("prev_hash"),
            "event_count": ledger.get("event_count", 1)}
