"""
REST alerts layer for the Stock Alerts dashboard.

Maps Lakehouse `final_transfer_sizewise` recommendations into the frontend
alert contract used by StockPulse_Agentfrontend (see mockAlerts.js).
"""

from __future__ import annotations

import base64
import json
import math
import time
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from lakehouse_client import record_stock_transfer, update_recommendation_status
from query_log import log_fetch
from sales_query import _load_dataset

# Cap mapped rows so the dashboard stays responsive (full table can be 10k+).
MAX_ALERTS = 500
_CACHE_TTL_SECONDS = 60
_alerts_cache: dict[str, Any] = {"ts": 0.0, "data": None}

STATUS_TO_UI = {
    "PENDING": "Open",
    "APPROVED": "Approved",
    "REJECTED": "Rejected",
}
UI_TO_STATUS = {
    "Open": "PENDING",
    "In Review": "PENDING",
    "Escalated": "PENDING",
    "Approved": "APPROVED",
    "Rejected": "REJECTED",
}

SEVERITIES = ["Critical", "Medium", "Low"]
UI_STATUSES = ["Open", "In Review", "Approved", "Rejected", "Escalated"]

# Derive zone/region for accordion grouping (lakehouse has city/state only)
STATE_TO_ZONE: dict[str, str] = {
    "HR": "North Zone",
    "UP": "North Zone",
    "DL": "North Zone",
    "PB": "North Zone",
    "RJ": "North Zone",
    "KA": "South Zone",
    "TN": "South Zone",
    "TS": "South Zone",
    "AP": "South Zone",
    "KL": "South Zone",
    "WB": "East Zone",
    "OD": "East Zone",
    "OR": "East Zone",
    "JH": "East Zone",
    "BR": "East Zone",
    "MH": "West Zone",
    "GJ": "West Zone",
    "GA": "West Zone",
}

STATE_TO_REGION: dict[str, str] = {
    "HR": "NCR", "UP": "NCR", "DL": "NCR",
    "KA": "South India", "TN": "South India", "TS": "South India",
    "AP": "South India", "KL": "South India",
    "WB": "East India", "OD": "East India", "OR": "East India",
    "JH": "East India", "BR": "East India",
    "MH": "West India", "GJ": "West India", "GA": "West India",
    "PB": "North India", "RJ": "North India",
}

# Retail brands — only these five store types exist in the transfer file.
KNOWN_STORE_TYPES: tuple[str, ...] = (
    "Pantaloons",
    "Shopper Stop",
    "Iconic",
    "Centro",
    "EBO",
)

_STORE_TYPE_ALIASES: dict[str, str] = {
    "pantaloons": "Pantaloons",
    "pantloons": "Pantaloons",
    "shopper stop": "Shopper Stop",
    "shopperstop": "Shopper Stop",
    "shoppers stop": "Shopper Stop",
    "iconic": "Iconic",
    "centro": "Centro",
    "ebo": "EBO",
    "ebo store": "EBO",
}


def _normalize_store_type(value: str) -> str:
    key = value.strip().lower()
    if not key or key == "n/a":
        return ""
    if key in _STORE_TYPE_ALIASES:
        return _STORE_TYPE_ALIASES[key]
    for canonical in KNOWN_STORE_TYPES:
        if canonical.lower() == key:
            return canonical
    return ""


def _derive_store_type(rec: dict) -> str:
    """Map receiver row to one of the five retail brands."""
    for col in ("store_type", "receiver_store_type", "storeType"):
        raw = rec.get(col)
        if raw is not None and str(raw).strip() and str(raw).strip().upper() != "N/A":
            normalized = _normalize_store_type(str(raw))
            if normalized:
                return normalized

    site_name = _safe(rec.get("receiver_site_name"), "")
    site_id = _safe(rec.get("receiver_site_id"), "")
    text = f"{site_name} {site_id}".lower()
    for alias, canonical in sorted(_STORE_TYPE_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in text:
            return canonical
    return ""


def _derive_zone(state: str) -> str:
    code = state.strip().upper() if state and state != "N/A" else ""
    return STATE_TO_ZONE.get(code, "Other Zone")


def _derive_region(state: str) -> str:
    code = state.strip().upper() if state and state != "N/A" else ""
    return STATE_TO_REGION.get(code, "Other")


def _as_filter_list(value: str | list[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).split(",") if v.strip()]


class StatusUpdateBody(BaseModel):
    ids: list[str] = Field(min_length=1)
    status: str


def _safe(val: Any, default: str = "N/A") -> str:
    if val is None:
        return default
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return default
    text = str(val).strip()
    return text if text and text.lower() != "nan" else default


def _num(val: Any, default: float = 0.0) -> float:
    try:
        n = float(val)
        if math.isnan(n) or math.isinf(n):
            return default
        return n
    except (TypeError, ValueError):
        return default


def _bool_flag(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    text = str(val).strip().lower()
    if text in ("1", "true", "yes", "y", "t"):
        return True
    if text in ("0", "false", "no", "n", "f", "n/a", ""):
        return False
    try:
        return float(text) == 1.0
    except (TypeError, ValueError):
        return False


def _transfer_scope(rec: dict) -> str:
    """Same city / same state / other state from lakehouse match flags."""
    if _bool_flag(rec.get("city_match")):
        return "Same City"
    if _bool_flag(rec.get("state_match")):
        return "Same State"
    if _bool_flag(rec.get("other_state")):
        return "Other State"
    return ""


def encode_alert_id(rec: dict) -> str:
    key = {
        "receiver_site_id": str(rec["receiver_site_id"]),
        "donor_site_id": str(rec["donor_site_id"]),
        "sku": str(rec["sku"]),
        "size": str(rec["size"]),
        "created_at": str(rec["created_at"]),
        "transfer_qty": float(rec["transfer_qty"]),
    }
    raw = json.dumps(key, separators=(",", ":")).encode()
    return "ALT-" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_alert_id(alert_id: str) -> dict:
    if not alert_id.startswith("ALT-"):
        raise HTTPException(status_code=400, detail="Invalid alert id")
    padded = alert_id[4:] + "=" * (-len(alert_id[4:]) % 4)
    try:
        key = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        key["transfer_qty"] = float(key["transfer_qty"])
        return key
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid alert id") from exc


def _severity(receiver_soh: float, priority_score: float) -> str:
    if receiver_soh <= 0:
        return "Critical"
    if priority_score >= 80 or receiver_soh < 3:
        return "Medium"
    return "Low"


def _parse_timestamp(created_at: Any) -> str:
    """Normalize lakehouse created_at into ISO-8601 for the frontend."""
    if created_at is None:
        return datetime.utcnow().isoformat() + "Z"

    # pandas / datetime objects
    if hasattr(created_at, "isoformat") and not isinstance(created_at, str):
        try:
            return created_at.isoformat()
        except Exception:
            pass

    text = _safe(created_at, "")
    if not text or text.upper() in ("NAT", "NONE", "NULL"):
        return datetime.utcnow().isoformat() + "Z"

    # Already ISO-ish
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        pass

    # Lakehouse format seen in final_transfer_sizewise: "14-07-2026 16:37"
    for fmt in (
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue

    return datetime.utcnow().isoformat() + "Z"


def recommendation_to_alert(rec: dict) -> dict:
    sku = _safe(rec.get("sku"), "UNKNOWN")
    size = _safe(rec.get("size"), "")
    product = f"{sku} ({size})" if size and size != "N/A" else sku

    receiver = _safe(rec.get("receiver_site_name"), "Unknown store")
    receiver_city = _safe(rec.get("receiver_city"), "")
    receiver_state = _safe(rec.get("receiver_state"), "")
    location = ", ".join(p for p in [receiver_city, receiver_state] if p and p != "N/A") or receiver_city or "-"

    donor = _safe(rec.get("donor_site_name"), "Unknown donor")
    donor_grade = _safe(rec.get("donor_store_grade"), "")
    donor_city = _safe(rec.get("donor_city"), "")
    donor_state = _safe(rec.get("donor_state"), "")
    receiver_grade = _safe(rec.get("receiver_store_grade"), "")

    qty = int(_num(rec.get("transfer_qty")))
    receiver_soh = int(_num(rec.get("receiver_soh")))
    donor_soh = int(_num(rec.get("donor_soh")))
    priority = _num(rec.get("priority_score"))
    required = int(_num(rec.get("required_qty"), qty))

    raw_status = _safe(rec.get("status"), "PENDING").upper()
    ui_status = STATUS_TO_UI.get(raw_status, "Open")
    severity = _severity(receiver_soh, priority)
    timestamp = _parse_timestamp(rec.get("created_at"))
    transfer_scope = _transfer_scope(rec)
    city_match = _bool_flag(rec.get("city_match"))
    state_match = _bool_flag(rec.get("state_match"))
    other_state = _bool_flag(rec.get("other_state"))

    # ASCII-only: Windows consoles / some proxies choke on unicode arrows.
    recommended_action = (
        f"Transfer {qty} units of {sku} ({size}) from {donor}"
        f"{f' [{donor_grade}]' if donor_grade != 'N/A' else ''} -> {receiver}"
        f"{f' [{receiver_grade}]' if receiver_grade != 'N/A' else ''}"
    )

    description = (
        f"Receiver {receiver}"
        f"{f' [{receiver_grade}]' if receiver_grade != 'N/A' else ''}: "
        f"needs {required} units of size {size} (SOH {receiver_soh}). "
        f"Transfer {qty} units from {donor}"
        f"{f' [{donor_grade}]' if donor_grade != 'N/A' else ''} "
        f"(donor SOH {donor_soh})."
    )

    # Lightweight history so the drawer chart still renders
    history = [
        {
            "date": timestamp[:10] if len(timestamp) >= 10 else datetime.utcnow().date().isoformat(),
            "stock": max(receiver_soh, 0),
        },
        {
            "date": datetime.utcnow().date().isoformat(),
            "stock": max(receiver_soh, 0),
        },
    ]

    activity = [
        {
            "id": "act-0",
            "event": "Transfer recommendation generated",
            "timestamp": timestamp,
            "actor": "Stockpulse",
        }
    ]

    return {
        "id": encode_alert_id(rec),
        "product": product,
        "sku": sku,
        "size": size if size != "N/A" else "",
        "store": receiver,
        "storeCode": _safe(rec.get("receiver_site_id"), ""),
        "city": receiver_city if receiver_city != "N/A" else "",
        "state": receiver_state if receiver_state != "N/A" else "",
        "storeType": _derive_store_type(rec),
        "receiverGrade": receiver_grade if receiver_grade != "N/A" else "",
        "zone": _derive_zone(receiver_state),
        "region": _derive_region(receiver_state),
        "warehouse": receiver,
        "location": location,
        "donorStore": donor,
        "donorStoreCode": _safe(rec.get("donor_site_id"), ""),
        "donorGrade": donor_grade if donor_grade != "N/A" else "",
        "donorCity": donor_city if donor_city != "N/A" else "",
        "donorState": donor_state if donor_state != "N/A" else "",
        "transferQty": qty,
        "requiredQty": required,
        "currentStock": receiver_soh,
        "receiverSoh": receiver_soh,
        "donorStock": donor_soh,
        "donorSoh": donor_soh,
        "cityMatch": city_match,
        "stateMatch": state_match,
        "otherState": other_state,
        "transferScope": transfer_scope,
        "minimumStock": max(required, receiver_soh + qty, 1),
        "forecast": max(0, receiver_soh + qty),
        "priorityScore": priority,
        "barcode": _safe(rec.get("barcode"), ""),
        "severity": severity,
        "status": ui_status,
        "recommendedAction": recommended_action,
        "timestamp": timestamp,
        "description": description,
        "history": history,
        "activity": activity,
        # Keep keys needed for approve/reject write-back (not shown in table)
        "_meta": {
            "receiver_site_id": str(rec.get("receiver_site_id")),
            "donor_site_id": str(rec.get("donor_site_id")),
            "receiver_site_name": receiver,
            "donor_site_name": donor,
            "size": size,
            "transfer_qty": qty,
            "created_at": str(rec.get("created_at")),
            "raw_status": raw_status,
        },
    }


async def _load_transfer_dataframe(*, force_refresh: bool = False):
    """Load final_transfer_sizewise from lakehouse."""
    now = time.monotonic()
    cache_key = "df"
    if (
        not force_refresh
        and _alerts_cache.get(cache_key) is not None
        and (now - _alerts_cache["ts"]) < _CACHE_TTL_SECONDS
    ):
        return _alerts_cache[cache_key]

    df, source = await _load_dataset("transfer_recommendations")
    log_fetch("alerts_list", source, "dashboard alerts")

    if df.empty:
        _alerts_cache[cache_key] = df
        _alerts_cache["data"] = []
        _alerts_cache["ts"] = now
        return df

    if "transfer_qty" in df.columns:
        df = df[df["transfer_qty"].fillna(0) > 0]

    if "priority_score" in df.columns:
        df = df.sort_values("priority_score", ascending=False)

    _alerts_cache[cache_key] = df
    _alerts_cache["ts"] = now
    return df


async def load_alerts(*, force_refresh: bool = False) -> list[dict]:
    now = time.monotonic()
    if (
        not force_refresh
        and _alerts_cache["data"] is not None
        and (now - _alerts_cache["ts"]) < _CACHE_TTL_SECONDS
    ):
        return _alerts_cache["data"]

    df = await _load_transfer_dataframe(force_refresh=force_refresh)
    if df.empty:
        _alerts_cache["data"] = []
        return []

    capped = df.head(MAX_ALERTS)
    records = capped.where(capped.notna(), None).to_dict(orient="records")
    alerts = [recommendation_to_alert(rec) for rec in records]

    _alerts_cache["data"] = alerts
    return alerts


async def load_store_alerts(
    *,
    store_id: str | None = None,
    store_name: str | None = None,
    force_refresh: bool = False,
) -> list[dict]:
    """All transfer recommendations for one receiver store from final_transfer_sizewise."""
    if not store_id and not store_name:
        raise HTTPException(status_code=400, detail="storeId or storeName required")

    df = await _load_transfer_dataframe(force_refresh=force_refresh)
    if df.empty:
        return []

    if store_id and "receiver_site_id" in df.columns:
        sid = str(store_id).strip()
        df = df[df["receiver_site_id"].astype(str).str.strip() == sid]
    elif store_name and "receiver_site_name" in df.columns:
        name = str(store_name).strip().lower()
        df = df[df["receiver_site_name"].astype(str).str.strip().str.lower() == name]

    if df.empty:
        return []

    records = df.where(df.notna(), None).to_dict(orient="records")
    return [recommendation_to_alert(rec) for rec in records]


def invalidate_alerts_cache() -> None:
    _alerts_cache["data"] = None
    _alerts_cache.pop("df", None)
    _alerts_cache["ts"] = 0.0


def _matches_multi(field_val: str, selected: list[str]) -> bool:
    if not selected:
        return True
    return field_val in selected


def apply_filters(alerts: list[dict], filters: dict) -> list[dict]:
    result = alerts

    search = (filters.get("search") or "").strip().lower()
    if search:
        result = [
            a
            for a in result
            if search in a["product"].lower()
            or search in a.get("store", a.get("warehouse", "")).lower()
            or search in a.get("warehouse", "").lower()
            or search in a.get("city", "").lower()
            or search in a.get("state", "").lower()
            or search in a.get("zone", "").lower()
            or search in a.get("region", "").lower()
            or search in a.get("storeType", "").lower()
            or search in a["location"].lower()
            or search in a["sku"].lower()
            or search in a["id"].lower()
            or search in a["recommendedAction"].lower()
            or search in a.get("donorStore", "").lower()
        ]

    severities = _as_filter_list(filters.get("severity"))
    if severities:
        result = [a for a in result if a["severity"] in severities]

    zones = _as_filter_list(filters.get("zone"))
    if zones:
        result = [a for a in result if _matches_multi(a.get("zone", ""), zones)]

    regions = _as_filter_list(filters.get("region"))
    if regions:
        result = [a for a in result if _matches_multi(a.get("region", ""), regions)]

    cities = _as_filter_list(filters.get("city"))
    if cities:
        result = [a for a in result if _matches_multi(a.get("city", ""), cities)]

    stores = _as_filter_list(filters.get("store"))
    if stores:
        result = [a for a in result if _matches_multi(a.get("store", a.get("warehouse", "")), stores)]

    store_types = _as_filter_list(filters.get("storeType"))
    if store_types:
        result = [a for a in result if _matches_multi(a.get("storeType", ""), store_types)]

    if filters.get("location"):
        locs = _as_filter_list(filters["location"])
        result = [a for a in result if a["location"] in locs]

    if filters.get("product"):
        products = _as_filter_list(filters["product"])
        result = [a for a in result if a["product"] in products]

    if filters.get("status"):
        result = [a for a in result if a["status"] == filters["status"]]

    store_id = (filters.get("storeId") or "").strip()
    if store_id:
        result = [a for a in result if str(a.get("storeCode", "")).strip() == store_id]

    if filters.get("dateFrom"):
        from_ts = datetime.fromisoformat(filters["dateFrom"]).timestamp()
        result = [
            a
            for a in result
            if _alert_ts(a) >= from_ts
        ]

    if filters.get("dateTo"):
        to_dt = datetime.fromisoformat(filters["dateTo"]).replace(
            hour=23, minute=59, second=59, microsecond=999000
        )
        to_ts = to_dt.timestamp()
        result = [a for a in result if _alert_ts(a) <= to_ts]

    return result


def _alert_ts(alert: dict) -> float:
    try:
        return datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def apply_sort(alerts: list[dict], sort_by: str | None, sort_dir: str) -> list[dict]:
    if not sort_by:
        return alerts

    reverse = (sort_dir or "desc").lower() != "asc"

    def key_fn(a: dict):
        val = a.get(sort_by)
        if sort_by == "timestamp":
            return _alert_ts(a)
        if isinstance(val, str):
            return val.lower()
        return val if val is not None else ""

    return sorted(alerts, key=key_fn, reverse=reverse)


def paginate(alerts: list[dict], page: int = 1, page_size: int = 10) -> dict:
    total = len(alerts)
    total_pages = max(1, math.ceil(total / page_size) if page_size else 1)
    safe_page = min(max(1, page), total_pages)
    start = (safe_page - 1) * page_size
    return {
        "data": alerts[start : start + page_size],
        "pagination": {
            "page": safe_page,
            "pageSize": page_size,
            "total": total,
            "totalPages": total_pages,
        },
    }


def compute_kpis(alerts: list[dict]) -> dict:
    return {
        "total": len(alerts),
        "critical": sum(1 for a in alerts if a["severity"] == "Critical"),
        "medium": sum(1 for a in alerts if a["severity"] == "Medium"),
        "low": sum(1 for a in alerts if a["severity"] == "Low"),
    }


def build_filter_options(alerts: list[dict]) -> dict:
    return {
        "severities": SEVERITIES,
        "locations": sorted({a["location"] for a in alerts if a.get("location")}),
        "products": sorted({a["product"] for a in alerts if a.get("product")}),
        "warehouses": sorted({a.get("store", a.get("warehouse", "")) for a in alerts if a.get("store") or a.get("warehouse")}),
        "zones": sorted({a.get("zone", "") for a in alerts if a.get("zone")}),
        "regions": sorted({a.get("region", "") for a in alerts if a.get("region")}),
        "cities": sorted({a.get("city", "") for a in alerts if a.get("city")}),
        "stores": sorted({a.get("store", "") for a in alerts if a.get("store")}),
        "storeTypes": list(KNOWN_STORE_TYPES),
        "statuses": UI_STATUSES,
    }


def public_alert(alert: dict) -> dict:
    """Strip internal _meta before sending to the UI."""
    return {k: v for k, v in alert.items() if k != "_meta"}


async def list_alerts_response(
    search: str | None = None,
    severity: str | None = None,
    location: str | None = None,
    product: str | None = None,
    status: str | None = None,
    zone: str | None = None,
    region: str | None = None,
    city: str | None = None,
    store: str | None = None,
    store_type: str | None = None,
    store_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort_by: str = "timestamp",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 10,
) -> dict:
    alerts = await load_alerts()
    filters = {
        "search": search,
        "severity": severity,
        "location": location,
        "product": product,
        "status": status,
        "zone": zone,
        "region": region,
        "city": city,
        "store": store,
        "storeType": store_type,
        "storeId": store_id,
        "dateFrom": date_from,
        "dateTo": date_to,
    }
    filtered = apply_filters(alerts, filters)
    sorted_alerts = apply_sort(filtered, sort_by, sort_dir)
    page_result = paginate(sorted_alerts, page, page_size)

    return {
        "data": [public_alert(a) for a in page_result["data"]],
        "pagination": page_result["pagination"],
        "kpis": compute_kpis(filtered),
        "filterOptions": build_filter_options(alerts),
    }


async def list_store_alerts_response(
    store_id: str | None = None,
    store_name: str | None = None,
    sort_by: str = "timestamp",
    sort_dir: str = "desc",
) -> dict:
    """All transfer alerts for one store from final_transfer_sizewise."""
    alerts = await load_store_alerts(store_id=store_id, store_name=store_name)
    sorted_alerts = apply_sort(alerts, sort_by, sort_dir)
    store_label = store_name or store_id or "Store"
    return {
        "store": {
            "name": store_label,
            "storeId": store_id or (alerts[0].get("storeCode") if alerts else ""),
            "city": alerts[0].get("city", "") if alerts else "",
            "state": alerts[0].get("state", "") if alerts else "",
            "zone": alerts[0].get("zone", "") if alerts else "",
        },
        "data": [public_alert(a) for a in sorted_alerts],
        "kpis": compute_kpis(sorted_alerts),
        "total": len(sorted_alerts),
    }


async def get_alert_by_id(alert_id: str) -> dict:
    alerts = await load_alerts()
    for alert in alerts:
        if alert["id"] == alert_id:
            return {"data": public_alert(alert)}
    raise HTTPException(status_code=404, detail="Alert not found")


async def update_alerts_status(ids: list[str], ui_status: str, decided_by: str = "web_user") -> dict:
    lakehouse_status = UI_TO_STATUS.get(ui_status)
    if lakehouse_status is None:
        raise HTTPException(status_code=400, detail=f"Unsupported status: {ui_status}")

    # In Review / Escalated map to PENDING — no lakehouse write
    if lakehouse_status == "PENDING" and ui_status != "Open":
        return {"success": True, "updated": 0, "message": f"{ui_status} is not persisted to Lakehouse"}

    if lakehouse_status == "PENDING":
        return {"success": True, "updated": 0}

    # Resolve donor/receiver names once before any status flips
    alerts_by_id = {a["id"]: a for a in await load_alerts()}

    updated = 0
    already_decided = 0

    for alert_id in ids:
        key = decode_alert_id(alert_id)
        match = alerts_by_id.get(alert_id)
        meta = (match or {}).get("_meta") or {}
        donor_name = meta.get("donor_site_name") or key["donor_site_id"]
        receiver_name = meta.get("receiver_site_name") or key["receiver_site_id"]

        result = await update_recommendation_status(
            receiver_site_id=key["receiver_site_id"],
            donor_site_id=key["donor_site_id"],
            sku=key["sku"],
            size=key["size"],
            created_at=key["created_at"],
            transfer_qty=key["transfer_qty"],
            status=lakehouse_status,
        )

        if result.get("already_decided"):
            already_decided += 1
            continue

        if lakehouse_status == "APPROVED":
            await record_stock_transfer(
                sku=key["sku"],
                from_store=donor_name,
                to_store=receiver_name,
                qty=int(key["transfer_qty"]),
                decided_by=decided_by,
            )

        updated += 1

    if updated:
        invalidate_alerts_cache()

    return {
        "success": True,
        "updated": updated,
        "already_decided": already_decided,
    }
