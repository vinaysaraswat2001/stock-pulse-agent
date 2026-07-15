import os
import uuid
import asyncio
import datetime
import pandas as pd
from deltalake import DeltaTable, write_deltalake
from deltalake.exceptions import CommitFailedError

from fabric_client import get_onelake_token, WORKSPACE_ID, LAKEHOUSE_ID
from query_log import log_fetch

# Table/column names — adjust these to match your actual Lakehouse schema.
STOCK_TABLE = os.getenv("FABRIC_STOCK_TABLE", "StockLevels")
STORE_COL   = "store_id"
SKU_COL     = "sku"
QTY_COL     = "qty"

TABLE_PATH = (
    f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/"
    f"{LAKEHOUSE_ID}/Tables/{STOCK_TABLE}"
)


def _storage_options() -> dict:
    return {"bearer_token": get_onelake_token(), "use_fabric_endpoint": "true"}


def _delta_row(store_id: str, sku: str, delta: int) -> pd.DataFrame:
    return pd.DataFrame([{STORE_COL: store_id, SKU_COL: sku, "delta": delta}])


def _merge_delta(dt: DeltaTable, store_id: str, sku: str, delta: int) -> None:
    (
        dt.merge(
            source=_delta_row(store_id, sku, delta),
            predicate=f"target.{STORE_COL} = source.{STORE_COL} AND target.{SKU_COL} = source.{SKU_COL}",
            source_alias="source",
            target_alias="target",
        )
        .when_matched_update(updates={QTY_COL: f"target.{QTY_COL} + source.delta"})
        .execute()
    )


def _sync_apply_transfer(from_store: str, to_store: str, sku: str, qty: int, max_retries: int = 3) -> None:
    if not LAKEHOUSE_ID:
        raise Exception("FABRIC_LAKEHOUSE_ID not configured — set it in .env")

    last_error = None
    for attempt in range(max_retries):
        try:
            dt = DeltaTable(TABLE_PATH, storage_options=_storage_options())
            _merge_delta(dt, from_store, sku, -qty)   # decrement source
            _merge_delta(dt, to_store, sku, qty)      # increment destination
            return
        except CommitFailedError as e:
            last_error = e
            print(f"[LAKEHOUSE] Commit conflict on attempt {attempt + 1}/{max_retries}: {e}")

    raise Exception(f"Stock update failed after {max_retries} retries: {last_error}")


async def update_stock_in_lakehouse(from_store: str, to_store: str, sku: str, qty: int) -> None:
    """Move `qty` units of `sku` from `from_store` to `to_store` in the Lakehouse."""
    await asyncio.to_thread(_sync_apply_transfer, from_store, to_store, sku, qty)


# ─── Generic item-master field update (dry-run by default) ──────
# Table was loaded from a headerless CSV, so columns are named _c0.._c46 —
# figure out the right key_column/target_column from sample rows before
# committing a real write.
ITEM_MASTER_TABLE = "item master updated"
ITEM_MASTER_PATH = (
    f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/"
    f"{LAKEHOUSE_ID}/Tables/dbo/{ITEM_MASTER_TABLE}"
)


def _sync_update_item_master_field(
    key_column: str, key_value: str, target_column: str, new_value: str, dry_run: bool = True
) -> dict:
    if not LAKEHOUSE_ID:
        raise Exception("FABRIC_LAKEHOUSE_ID not configured — set it in .env")

    dt = DeltaTable(ITEM_MASTER_PATH, storage_options=_storage_options())
    df = dt.to_pyarrow_table().to_pandas()

    matches = df[df[key_column] == key_value]
    if matches.empty:
        return {"matched_rows": 0, "preview": [], "committed": False}

    preview = matches[[key_column, target_column]].to_dict(orient="records")

    if dry_run:
        return {"matched_rows": len(matches), "preview": preview, "committed": False}

    source = pd.DataFrame([{key_column: key_value, "new_value": new_value}])
    (
        dt.merge(
            source=source,
            predicate=f"target.{key_column} = source.{key_column}",
            source_alias="source",
            target_alias="target",
        )
        .when_matched_update(updates={target_column: "source.new_value"})
        .execute()
    )
    return {"matched_rows": len(matches), "preview": preview, "committed": True}


async def update_item_master_field(
    key_column: str, key_value: str, target_column: str, new_value: str, dry_run: bool = True
) -> dict:
    """Update `target_column` to `new_value` for rows where `key_column == key_value`
    in the 'item master updated' table. dry_run=True (default) previews the matching
    rows' current values without writing anything."""
    return await asyncio.to_thread(
        _sync_update_item_master_field, key_column, key_value, target_column, new_value, dry_run
    )


# ─── Stock transfer audit log ────────────────────────────────────
# Approved transfers (from Teams Approve/Reject cards) are appended here as
# a durable record. This does NOT touch the Spark pipeline's own SOH export —
# it's a separate ledger of what the bot was told to move.
STOCK_TRANSFERS_TABLE = "stock_transfers"
STOCK_TRANSFERS_PATH = (
    f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/"
    f"{LAKEHOUSE_ID}/Tables/dbo/{STOCK_TRANSFERS_TABLE}"
)


def _sync_record_stock_transfer(
    sku: str, from_store: str, to_store: str, qty: int, decided_by: str
) -> dict:
    if not LAKEHOUSE_ID:
        raise Exception("FABRIC_LAKEHOUSE_ID not configured — set it in .env")

    row = {
        "transfer_id": str(uuid.uuid4()),
        "sku": sku,
        "from_store": from_store,
        "to_store": to_store,
        "qty": qty,
        "status": "approved",
        "decided_by": decided_by,
        "decided_at": datetime.datetime.utcnow().isoformat(),
    }
    write_deltalake(
        STOCK_TRANSFERS_PATH,
        pd.DataFrame([row]),
        mode="append",
        storage_options=_storage_options(),
    )
    log_fetch("stock_transfer_write", f"Lakehouse {LAKEHOUSE_ID} -> Tables/dbo/{STOCK_TRANSFERS_TABLE}", f"{sku} {from_store}->{to_store} qty={qty}")
    return row


async def record_stock_transfer(
    sku: str, from_store: str, to_store: str, qty: int, decided_by: str = "teams_user"
) -> dict:
    """Append an approved transfer to Tables/dbo/stock_transfers (creates the
    table on first use)."""
    return await asyncio.to_thread(
        _sync_record_stock_transfer, sku, from_store, to_store, qty, decided_by
    )
