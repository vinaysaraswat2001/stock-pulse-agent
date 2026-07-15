import io
import asyncio
import httpx
import pandas as pd

from fabric_client import get_onelake_token, WORKSPACE_ID, LAKEHOUSE_ID, ONELAKE_DFS_HOST
from query_log import log_fetch

# Spark-written CSV export with real sales quantities/amounts per SKU.
# Schema: Site, SKU, Season, Color, DEPARTMENT, Date, total_qty, total_amt,
#         First_Purchase_Date, First_180_Days_Purchase_Qty, Days_From_Purchase
SALES_EXPORT_DIR = "Files/output/date_groupby_sales_export"


async def _list_part_files(directory: str) -> list[str]:
    token = get_onelake_token()
    url = f"{ONELAKE_DFS_HOST}/{WORKSPACE_ID}?resource=filesystem&directory={LAKEHOUSE_ID}/{directory}&recursive=false"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}", "x-ms-version": "2023-11-03"})
        r.raise_for_status()
        paths = r.json().get("paths", [])
    return [p["name"] for p in paths if p["name"].endswith(".csv") and not p.get("isDirectory")]


async def _fetch_csv(path: str) -> pd.DataFrame:
    token = get_onelake_token()
    url = f"{ONELAKE_DFS_HOST}/{WORKSPACE_ID}/{path}"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}", "x-ms-version": "2023-11-03"})
        r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content))


async def _load_sales_export() -> tuple[pd.DataFrame, list[str]]:
    if not LAKEHOUSE_ID:
        raise Exception("FABRIC_LAKEHOUSE_ID not configured — set it in .env")

    files = await _list_part_files(SALES_EXPORT_DIR)
    dfs = await asyncio.gather(*[_fetch_csv(f) for f in files])
    return pd.concat(dfs, ignore_index=True), files


async def get_top_skus(n: int = 10, by: str = "qty", question: str = "") -> list[dict]:
    """Top-N SKUs across the whole sales export, ranked by total quantity sold
    (by='qty') or total revenue (by='amt')."""
    df, files = await _load_sales_export()
    log_fetch(
        "top_skus",
        f"Lakehouse {LAKEHOUSE_ID} -> {SALES_EXPORT_DIR}/ ({len(files)} CSV part files)",
        question,
    )
    metric_col = "total_qty" if by == "qty" else "total_amt"

    grouped = df.groupby("SKU", as_index=False)[["total_qty", "total_amt"]].sum()
    grouped = grouped.sort_values(metric_col, ascending=False).head(n)

    return grouped.to_dict(orient="records")


def format_top_skus(rows: list[dict]) -> str:
    if not rows:
        return "Koi sales data nahi mila."

    lines = ["📊 **Top SKUs by quantity sold:**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(
            f"{i}. **{row['SKU']}** — {int(row['total_qty'])} units sold, ₹{row['total_amt']:,.0f} revenue"
        )
    return "\n".join(lines)


async def get_sku_count(question: str = "") -> int:
    """Count of distinct SKUs that appear in the sales export."""
    df, files = await _load_sales_export()
    log_fetch(
        "sku_count",
        f"Lakehouse {LAKEHOUSE_ID} -> {SALES_EXPORT_DIR}/ ({len(files)} CSV part files)",
        question,
    )
    return int(df["SKU"].nunique())


async def get_top_stores(n: int = 10, by: str = "amt", question: str = "") -> list[dict]:
    """Top-N stores (Site) across the sales export, ranked by total revenue
    (by='amt') or total quantity sold (by='qty')."""
    df, files = await _load_sales_export()
    log_fetch(
        "top_stores",
        f"Lakehouse {LAKEHOUSE_ID} -> {SALES_EXPORT_DIR}/ ({len(files)} CSV part files)",
        question,
    )
    metric_col = "total_qty" if by == "qty" else "total_amt"

    grouped = df.groupby("Site", as_index=False)[["total_qty", "total_amt"]].sum()
    grouped = grouped.sort_values(metric_col, ascending=False).head(n)

    return grouped.to_dict(orient="records")


def format_top_stores(rows: list[dict]) -> str:
    if not rows:
        return "Koi sales data nahi mila."

    lines = ["🏬 **Best performing stores by revenue:**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(
            f"{i}. **{row['Site']}** — ₹{row['total_amt']:,.0f} revenue, {int(row['total_qty'])} units sold"
        )
    return "\n".join(lines)


# Store+SKU+month level stock-on-hand vs. sales.
# Schema: Site, SKU, Season, Year, Month, sales, purchase, first_sale_month,
#         cum_purchase, cum_sales, opening_stock, total_stock, valid_sales,
#         closing_stock, soh
SOH_PATH = "Files/output/soh_result_new9.csv"


async def _load_soh() -> pd.DataFrame:
    if not LAKEHOUSE_ID:
        raise Exception("FABRIC_LAKEHOUSE_ID not configured — set it in .env")
    return await _fetch_csv(f"{LAKEHOUSE_ID}/{SOH_PATH}")


async def get_dead_stock(n: int = 15, store: str | None = None, question: str = "") -> dict:
    """Items with stock on hand (soh > 0) but zero sales (sales == 0) in the
    most recent month present in the data. Optionally filter to one store
    (substring match on Site)."""
    df = await _load_soh()
    log_fetch("dead_stock", f"Lakehouse {LAKEHOUSE_ID} -> {SOH_PATH}", question)

    latest_year, latest_month = df[["Year", "Month"]].drop_duplicates().sort_values(
        ["Year", "Month"]
    ).iloc[-1]

    period_df = df[(df["Year"] == latest_year) & (df["Month"] == latest_month)]
    dead = period_df[(period_df["soh"] > 0) & (period_df["sales"] == 0)]

    if store:
        dead = dead[dead["Site"].str.contains(store, case=False, na=False)]

    dead = dead.sort_values("soh", ascending=False).head(n)

    return {
        "period": f"{int(latest_year)}-{int(latest_month):02d}",
        "rows": dead[["Site", "SKU", "soh"]].to_dict(orient="records"),
    }


def format_dead_stock(result: dict) -> str:
    rows = result["rows"]
    if not rows:
        return f"Koi dead stock nahi mila ({result['period']} ke liye)."

    lines = [f"📦 **Dead stock ({result['period']}, no sales this month):**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. **{row['SKU']}** at {row['Site']} — {int(row['soh'])} units sitting unsold")
    return "\n".join(lines)


async def get_transfer_plan(sku: str, question: str = "") -> dict | None:
    """For a given SKU: find the store sitting on dead stock (soh > 0, sales == 0
    this month) and the store where this SKU actually sells best, and propose
    moving the dead stock there. Returns None if there's nothing to transfer
    (no dead stock for this SKU, or it's already at the best-selling store)."""
    soh_df = await _load_soh()
    log_fetch("transfer_plan", f"Lakehouse {LAKEHOUSE_ID} -> {SOH_PATH}", question)

    latest_year, latest_month = soh_df[["Year", "Month"]].drop_duplicates().sort_values(
        ["Year", "Month"]
    ).iloc[-1]

    period_df = soh_df[(soh_df["Year"] == latest_year) & (soh_df["Month"] == latest_month)]
    sku_df = period_df[period_df["SKU"].str.upper() == sku.upper()]
    dead = sku_df[(sku_df["soh"] > 0) & (sku_df["sales"] == 0)].sort_values("soh", ascending=False)

    if dead.empty:
        return None

    sales_df, files = await _load_sales_export()
    log_fetch(
        "transfer_plan",
        f"Lakehouse {LAKEHOUSE_ID} -> {SALES_EXPORT_DIR}/ ({len(files)} CSV part files)",
        question,
    )
    sku_sales = sales_df[sales_df["SKU"].str.upper() == sku.upper()]
    if sku_sales.empty:
        return None

    best = sku_sales.groupby("Site", as_index=False)["total_qty"].sum().sort_values(
        "total_qty", ascending=False
    ).iloc[0]
    to_store = best["Site"]

    candidates = dead[dead["Site"] != to_store]
    if candidates.empty:
        return None  # dead stock is already sitting at the best-selling store

    source = candidates.iloc[0]
    return {
        "sku": sku,
        "from_store": source["Site"],
        "to_store": to_store,
        "qty": int(source["soh"]),
        "period": f"{int(latest_year)}-{int(latest_month):02d}",
    }
