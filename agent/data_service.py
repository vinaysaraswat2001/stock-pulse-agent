"""
Mock data service — Phase 1–3.
Later swap implementation for Fabric Lakehouse without changing router/contracts.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MOCK_PATH = Path(__file__).resolve().parent / "mock_data" / "alerts.json"
_cache: dict[str, Any] | None = None
_mutations: dict[str, str] = {}  # transferId -> APPROVED|REJECTED


def _load() -> dict[str, Any]:
    global _cache
    if _cache is None:
        with open(_MOCK_PATH, encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def reload_mock_data() -> None:
    global _cache
    _cache = None
    _mutations.clear()


def get_summary() -> dict[str, Any]:
    return deepcopy(_load()["summary"])


def get_stores(severity: str | None = None) -> list[dict[str, Any]]:
    stores = deepcopy(_load()["stores"])
    if not severity:
        return stores
    key = severity.lower()
    if key not in ("critical", "medium", "low"):
        return stores
    filtered = [s for s in stores if s.get(key, 0) > 0]
    filtered.sort(key=lambda s: s.get(key, 0), reverse=True)
    return filtered


def get_store(store_id: str) -> dict[str, Any] | None:
    for store in _load()["stores"]:
        if store["id"] == store_id:
            return deepcopy(store)
    return None


def get_transfers(store_id: str) -> list[dict[str, Any]]:
    raw = deepcopy(_load()["transfers"].get(store_id, []))
    for t in raw:
        status = _mutations.get(t["id"])
        if status:
            t["status"] = status
    return raw


def get_transfer(store_id: str, transfer_id: str) -> dict[str, Any] | None:
    for t in get_transfers(store_id):
        if t["id"] == transfer_id:
            return t
    return None


def update_transfer_status(transfer_id: str, status: str) -> bool:
    data = _load()
    for transfers in data["transfers"].values():
        for t in transfers:
            if t["id"] == transfer_id:
                _mutations[transfer_id] = status
                return True
    return False


def utc_now_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def display_date_label() -> str:
    """Human date for decision cards, e.g. 6 Aug 2026."""
    now = datetime.now(timezone.utc)
    return f"{now.day} {now.strftime('%b %Y')}"
