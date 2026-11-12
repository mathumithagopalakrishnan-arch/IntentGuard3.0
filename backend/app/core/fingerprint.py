"""Canonical JSON + SHA-256. A hash proves the data was not changed.
It does NOT prove the merchant's claims are true."""
import hashlib
import json
from typing import Any


def canonical_json(data: Any) -> str:
    # Sorted keys, no extra spaces, real unicode (Tamil/Hindi stay stable).
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def intent_fingerprint(intent: dict) -> str:
    return sha256_hex({"type": "intent_passport", "v": 1, "intent": intent})
