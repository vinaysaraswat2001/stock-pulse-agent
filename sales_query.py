import io
import asyncio
import httpx
import pandas as pd
from deltalake import DeltaTable

from fabric_client import get_onelake_token, WORKSPACE_ID, LAKEHOUSE_ID, ONELAKE_DFS_HOST
from query_log import log_fetch
from datasets import DATASETS

# _c# -> real column name, for the headerless item_master Delta table (see datasets.py)
ITEM_MASTER_COLS = {
    "icode": "_c1", "barcode": "_c2", "sku_code": "_c4", "size": "_c6",
    "department": "_c14", "hsn_code": "_c35", "std_rate": "_c37",
    "wsp": "_c38", "rsp": "_c39", "mrp": "_c40", "vendor_name": "_c41",
}


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


async def _load_dataset(name: str) -> tuple[pd.DataFrame, str]:
    """Load a registered CSV dataset (file or partitioned dir) from datasets.py.
    Returns (dataframe, human-readable source description for logging)."""
    if not LAKEHOUSE_ID:
        raise Exception("FABRIC_LAKEHOUSE_ID not configured — set it in .env")

    meta = DATASETS[name]
    if meta["type"] == "dir":
        files = await _list_part_files(meta["path"])
        dfs = await asyncio.gather(*[_fetch_csv(f) for f in files])
        df = pd.concat(dfs, ignore_index=True)
        source = f"Lakehouse {LAKEHOUSE_ID} -> {meta['path']}/ ({len(files)} CSV part files)"
    elif meta["type"] == "file":
        df = await _fetch_csv(f"{LAKEHOUSE_ID}/{meta['path']}")
        source = f"Lakehouse {LAKEHOUSE_ID} -> {meta['path']}"
    elif meta["type"] == "delta_table":
        token = get_onelake_token()
        path = f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{LAKEHOUSE_ID}/{meta['path']}"
        df = await asyncio.to_thread(
            lambda: DeltaTable(
                path, storage_options={"bearer_token": token, "use_fabric_endpoint": "true"}
            ).to_pyarrow_table().to_pandas()
        )
        source = f"Lakehouse {LAKEHOUSE_ID} -> {meta['path']}"
    else:
        raise ValueError(f"_load_dataset doesn't support type {meta['type']!r} for {name!r}")

    return df, source


async def get_top_skus(n: int = 10, by: str = "qty", question: str = "") -> list[dict]:
    """Top-N SKUs across the whole sales export, ranked by total quantity sold
    (by='qty') or total revenue (by='amt')."""
    df, source = await _load_dataset("sales_export")
    log_fetch("top_skus", source, question)
    metric_col = "total_qty" if by == "qty" else "total_amt"

    grouped = df.groupby("SKU", as_index=False)[["total_qty", "total_amt"]].sum()
    grouped = grouped.sort_values(metric_col, ascending=False).head(n)

    return grouped.to_dict(orient="records")


def format_top_skus(rows: list[dict]) -> str:
    if not rows:
        return "No sales data found."

    lines = ["📊 **Top SKUs by quantity sold:**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(
            f"{i}. **{row['SKU']}** — {int(row['total_qty'])} units sold, ₹{row['total_amt']:,.0f} revenue"
        )
    return "\n".join(lines)


async def get_sku_count(question: str = "") -> int:
    """Count of distinct SKUs that appear in the sales export."""
    df, source = await _load_dataset("sales_export")
    log_fetch("sku_count", source, question)
    return int(df["SKU"].nunique())


async def get_top_stores(n: int = 10, by: str = "amt", question: str = "") -> list[dict]:
    """Top-N stores (Site) across the sales export, ranked by total revenue
    (by='amt') or total quantity sold (by='qty')."""
    df, source = await _load_dataset("sales_export")
    log_fetch("top_stores", source, question)
    metric_col = "total_qty" if by == "qty" else "total_amt"

    grouped = df.groupby("Site", as_index=False)[["total_qty", "total_amt"]].sum()
    grouped = grouped.sort_values(metric_col, ascending=False).head(n)

    return grouped.to_dict(orient="records")


def format_top_stores(rows: list[dict]) -> str:
    if not rows:
        return "No sales data found."

    lines = ["🏬 **Best performing stores by revenue:**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(
            f"{i}. **{row['Site']}** — ₹{row['total_amt']:,.0f} revenue, {int(row['total_qty'])} units sold"
        )
    return "\n".join(lines)


async def get_dead_stock(n: int = 15, store: str | None = None, question: str = "") -> dict:
    """Items with stock on hand (soh > 0) but zero sales (sales == 0) in the
    most recent month present in the data. Optionally filter to one store
    (substring match on Site)."""
    df, source = await _load_dataset("soh_monthly")
    log_fetch("dead_stock", source, question)

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
        return f"No dead stock found for {result['period']}."

    lines = [f"📦 **Dead stock ({result['period']}, no sales this month):**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. **{row['SKU']}** at {row['Site']} — {int(row['soh'])} units sitting unsold")
    return "\n".join(lines)


async def get_transfer_plan(sku: str, question: str = "") -> dict | None:
    """For a given SKU: find the store sitting on dead stock (soh > 0, sales == 0
    this month) and the store where this SKU actually sells best, and propose
    moving the dead stock there. Returns None if there's nothing to transfer
    (no dead stock for this SKU, or it's already at the best-selling store)."""
    soh_df, soh_source = await _load_dataset("soh_monthly")
    log_fetch("transfer_plan", soh_source, question)

    latest_year, latest_month = soh_df[["Year", "Month"]].drop_duplicates().sort_values(
        ["Year", "Month"]
    ).iloc[-1]

    period_df = soh_df[(soh_df["Year"] == latest_year) & (soh_df["Month"] == latest_month)]
    sku_df = period_df[period_df["SKU"].str.upper() == sku.upper()]
    dead = sku_df[(sku_df["soh"] > 0) & (sku_df["sales"] == 0)].sort_values("soh", ascending=False)

    if dead.empty:
        return None

    sales_df, sales_source = await _load_dataset("sales_export")
    log_fetch("transfer_plan", sales_source, question)
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


def _latest_period(df: pd.DataFrame) -> tuple[int, int]:
    y, m = df[["Year", "Month"]].drop_duplicates().sort_values(["Year", "Month"]).iloc[-1]
    return int(y), int(m)


async def get_sell_through_rate(n: int = 10, question: str = "") -> dict:
    """Fastest-moving SKUs this period: cum_sales / cum_purchase, at the most
    recent Year/Month snapshot, summed across all stores per SKU."""
    df, source = await _load_dataset("soh_monthly")
    log_fetch("sell_through_rate", source, question)

    year, month = _latest_period(df)
    period_df = df[(df["Year"] == year) & (df["Month"] == month)]

    grouped = period_df.groupby("SKU", as_index=False)[["cum_sales", "cum_purchase"]].sum()
    grouped = grouped[grouped["cum_purchase"] > 0]
    grouped["sell_through"] = grouped["cum_sales"] / grouped["cum_purchase"]
    grouped = grouped.sort_values("sell_through", ascending=False).head(n)

    return {"period": f"{year}-{month:02d}", "rows": grouped.to_dict(orient="records")}


def format_sell_through_rate(result: dict) -> str:
    rows = result["rows"]
    if not rows:
        return "No sell-through data found."
    lines = [f"⚡ **Fastest sell-through SKUs ({result['period']}):**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. **{row['SKU']}** — {row['sell_through']*100:.0f}% sold through")
    return "\n".join(lines)


async def get_dead_stock_totals(n: int = 15, question: str = "") -> dict:
    """Total dead stock (soh > 0, sales == 0 this month) per SKU, summed across
    all stores it's stuck in."""
    df, source = await _load_dataset("soh_monthly")
    log_fetch("dead_stock_totals", source, question)

    year, month = _latest_period(df)
    period_df = df[(df["Year"] == year) & (df["Month"] == month)]
    dead = period_df[(period_df["soh"] > 0) & (period_df["sales"] == 0)]

    grouped = dead.groupby("SKU", as_index=False).agg(
        total_soh=("soh", "sum"), store_count=("Site", "nunique")
    ).sort_values("total_soh", ascending=False).head(n)

    return {"period": f"{year}-{month:02d}", "rows": grouped.to_dict(orient="records")}


def format_dead_stock_totals(result: dict) -> str:
    rows = result["rows"]
    if not rows:
        return f"No dead stock found for {result['period']}."
    lines = [f"📦 **Total dead stock by SKU ({result['period']}):**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(
            f"{i}. **{row['SKU']}** — {int(row['total_soh'])} units dead across {int(row['store_count'])} store(s)"
        )
    return "\n".join(lines)


async def get_department_discount_stats(question: str = "") -> list[dict]:
    """Average discount % and total revenue per DEPARTMENT, across all weeks
    in the discount dataset."""
    df, source = await _load_dataset("soh_weekly_discount")
    log_fetch("department_discount", source, question)

    grouped = df.groupby("DEPARTMENT", as_index=False).agg(
        avg_discount=("weekly_avg_discount", "mean"),
        total_revenue=("weekly_total_revenue", "sum"),
    )
    return grouped.to_dict(orient="records")


def format_lowest_discount_categories(rows: list[dict], n: int = 10) -> str:
    if not rows:
        return "No discount data found."
    rows = sorted(rows, key=lambda r: r["avg_discount"])[:n]
    lines = ["🏷️ **Lowest average discount by category:**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. **{row['DEPARTMENT']}** — {row['avg_discount']:.1f}% avg discount")
    return "\n".join(lines)


def format_avg_discount_by_department(rows: list[dict], n: int = 15) -> str:
    if not rows:
        return "No discount data found."
    rows = sorted(rows, key=lambda r: r["avg_discount"], reverse=True)[:n]
    lines = ["🏷️ **Average discount % per department:**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. **{row['DEPARTMENT']}** — {row['avg_discount']:.1f}% avg discount")
    return "\n".join(lines)


async def get_below_average_sales(n: int = 15, days: int = 30, question: str = "") -> dict:
    """SKUs whose total quantity sold in the last `days` (from the latest date
    in the data) is below the average across all SKUs in that window."""
    df, source = await _load_dataset("sales_export")
    log_fetch("below_average_sales", source, question)

    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
    max_date = df["Date"].max()
    window_df = df[df["Date"] >= max_date - pd.Timedelta(days=days)]

    grouped = window_df.groupby("SKU", as_index=False)["total_qty"].sum()
    avg_qty = grouped["total_qty"].mean()
    below = grouped[grouped["total_qty"] < avg_qty].sort_values("total_qty").head(n)

    return {
        "days": days,
        "average_qty": round(avg_qty, 1),
        "rows": below.to_dict(orient="records"),
    }


def format_below_average_sales(result: dict) -> str:
    rows = result["rows"]
    if not rows:
        return f"No SKUs found below average sales (last {result['days']} days)."
    lines = [
        f"📉 **Below-average sales, last {result['days']} days** "
        f"(avg = {result['average_qty']} units/SKU):\n"
    ]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. **{row['SKU']}** — {int(row['total_qty'])} units sold")
    return "\n".join(lines)


async def get_stockouts(n: int = 15, store: str | None = None, question: str = "") -> dict:
    """Store+SKU combinations with zero stock on hand in the latest month."""
    df, source = await _load_dataset("soh_monthly")
    log_fetch("stockouts", source, question)

    year, month = _latest_period(df)
    period_df = df[(df["Year"] == year) & (df["Month"] == month)]
    out = period_df[period_df["soh"] <= 0]

    if store:
        out = out[out["Site"].str.contains(store, case=False, na=False)]

    out = out.head(n)
    return {"period": f"{year}-{month:02d}", "rows": out[["Site", "SKU"]].to_dict(orient="records")}


def format_stockouts(result: dict) -> str:
    rows = result["rows"]
    if not rows:
        return f"No stockouts found for {result['period']}."
    lines = [f"🚫 **Current stockouts ({result['period']}):**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. **{row['SKU']}** at {row['Site']}")
    return "\n".join(lines)


async def get_markdown_candidates(n: int = 15, question: str = "") -> dict:
    """SKUs to prioritize for markdown: low sell-through rate combined with
    high remaining stock on hand, this period."""
    df, source = await _load_dataset("soh_monthly")
    log_fetch("markdown_candidates", source, question)

    year, month = _latest_period(df)
    period_df = df[(df["Year"] == year) & (df["Month"] == month)]

    grouped = period_df.groupby("SKU", as_index=False).agg(
        soh=("soh", "sum"), cum_sales=("cum_sales", "sum"), cum_purchase=("cum_purchase", "sum")
    )
    grouped = grouped[(grouped["soh"] > 0) & (grouped["cum_purchase"] > 0)]
    grouped["sell_through"] = grouped["cum_sales"] / grouped["cum_purchase"]
    grouped["markdown_score"] = grouped["soh"] / (grouped["sell_through"] + 0.01)
    grouped = grouped.sort_values("markdown_score", ascending=False).head(n)

    return {"period": f"{year}-{month:02d}", "rows": grouped.to_dict(orient="records")}


def format_markdown_candidates(result: dict) -> str:
    rows = result["rows"]
    if not rows:
        return f"No markdown candidates found for {result['period']}."
    lines = [f"🔻 **Markdown priority SKUs ({result['period']}, slow movement + high stock):**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(
            f"{i}. **{row['SKU']}** — {row['sell_through']*100:.0f}% sell-through, {int(row['soh'])} units on hand"
        )
    return "\n".join(lines)


async def get_stock_coverage_days(n: int = 10, question: str = "") -> list[dict]:
    """Days-of-cover per department: soh / (average daily sell rate), for the
    highest-volume departments."""
    df, source = await _load_dataset("soh_weekly_discount")
    log_fetch("stock_coverage_days", source, question)

    grouped = df.groupby("DEPARTMENT", as_index=False).agg(
        soh=("soh", "sum"), weekly_qty=("weekly_qty", "sum")
    )
    grouped = grouped[grouped["weekly_qty"] > 0]
    grouped["coverage_days"] = grouped["soh"] / (grouped["weekly_qty"] / 7)
    grouped = grouped.sort_values("weekly_qty", ascending=False).head(n)

    return grouped.to_dict(orient="records")


def format_stock_coverage_days(rows: list[dict]) -> str:
    if not rows:
        return "No stock coverage data found."
    lines = ["📆 **Stock coverage (days) — top categories by volume:**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. **{row['DEPARTMENT']}** — {row['coverage_days']:.0f} days of cover")
    return "\n".join(lines)


async def get_purchase_sales_gap(n: int = 10, question: str = "") -> dict:
    """Stores with the largest gap between cumulative purchases and cumulative
    sales this period (i.e. receiving much more than they're selling)."""
    df, source = await _load_dataset("soh_monthly")
    log_fetch("purchase_sales_gap", source, question)

    year, month = _latest_period(df)
    period_df = df[(df["Year"] == year) & (df["Month"] == month)]

    grouped = period_df.groupby("Site", as_index=False)[["cum_purchase", "cum_sales"]].sum()
    grouped["gap"] = grouped["cum_purchase"] - grouped["cum_sales"]
    grouped = grouped.sort_values("gap", ascending=False).head(n)

    return {"period": f"{year}-{month:02d}", "rows": grouped.to_dict(orient="records")}


def format_purchase_sales_gap(result: dict) -> str:
    rows = result["rows"]
    if not rows:
        return f"No purchase/sales gap data found for {result['period']}."
    lines = [f"📊 **Largest purchase-vs-sales gap by store ({result['period']}):**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(
            f"{i}. **{row['Site']}** — {int(row['gap'])} units gap "
            f"({int(row['cum_purchase'])} purchased, {int(row['cum_sales'])} sold)"
        )
    return "\n".join(lines)


async def get_overstocked_products(n: int = 10, question: str = "") -> dict:
    """SKUs with the highest stock-to-sales ratio this period — sitting on far
    more stock than current sales pace justifies."""
    df, source = await _load_dataset("soh_monthly")
    log_fetch("overstocked_products", source, question)

    year, month = _latest_period(df)
    period_df = df[(df["Year"] == year) & (df["Month"] == month)]

    grouped = period_df.groupby("SKU", as_index=False).agg(soh=("soh", "sum"), sales=("sales", "sum"))
    grouped = grouped[grouped["soh"] >= 10]
    grouped["ratio"] = grouped["soh"] / grouped["sales"].clip(lower=1)
    grouped = grouped.sort_values("ratio", ascending=False).head(n)

    return {"period": f"{year}-{month:02d}", "rows": grouped.to_dict(orient="records")}


def format_overstocked_products(result: dict) -> str:
    rows = result["rows"]
    if not rows:
        return f"No overstocked products found for {result['period']}."
    lines = [f"📦 **Overstocked products ({result['period']}):**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. **{row['SKU']}** — {int(row['soh'])} units on hand vs {int(row['sales'])} sold this month")
    return "\n".join(lines)


async def get_full_price_sales_by_store(n: int = 10, question: str = "") -> list[dict]:
    """Stores generating the most revenue at (near) zero discount."""
    df, source = await _load_dataset("soh_weekly_discount")
    log_fetch("full_price_sales", source, question)

    full_price = df[df["weekly_avg_discount"] <= 1]
    grouped = full_price.groupby("Site", as_index=False)["weekly_total_revenue"].sum()
    grouped = grouped.sort_values("weekly_total_revenue", ascending=False).head(n)

    return grouped.to_dict(orient="records")


def format_full_price_sales_by_store(rows: list[dict]) -> str:
    if not rows:
        return "No full-price sales data found."
    lines = ["💯 **Highest full-price sales by store:**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. **{row['Site']}** — ₹{row['weekly_total_revenue']:,.0f} at full price")
    return "\n".join(lines)


async def get_sku_contribution(n: int = 10, question: str = "") -> list[dict]:
    """Each SKU's % contribution to total revenue across the sales export."""
    df, source = await _load_dataset("sales_export")
    log_fetch("sku_contribution", source, question)

    grouped = df.groupby("SKU", as_index=False)["total_amt"].sum()
    grand_total = grouped["total_amt"].sum()
    grouped["contribution_pct"] = grouped["total_amt"] / grand_total * 100
    grouped = grouped.sort_values("total_amt", ascending=False).head(n)

    return grouped.to_dict(orient="records")


def format_sku_contribution(rows: list[dict]) -> str:
    if not rows:
        return "No sales data found."
    lines = ["📈 **SKU contribution to total sales:**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. **{row['SKU']}** — {row['contribution_pct']:.1f}% of total revenue (₹{row['total_amt']:,.0f})")
    return "\n".join(lines)


async def get_most_profitable_skus(n: int = 10, days: int = 90, question: str = "") -> dict:
    """Approximate SKU profitability over the last `days`: revenue from the
    sales export minus (WSP cost from item master x quantity sold). WSP is used
    as a cost proxy — not true landed cost — so treat this as directional."""
    sales_df, sales_source = await _load_dataset("sales_export")
    log_fetch("most_profitable_skus", sales_source, question)

    sales_df = sales_df.copy()
    sales_df["Date"] = pd.to_datetime(sales_df["Date"], errors="coerce", utc=True)
    max_date = sales_df["Date"].max()
    window_df = sales_df[sales_df["Date"] >= max_date - pd.Timedelta(days=days)]
    revenue = window_df.groupby("SKU", as_index=False)[["total_qty", "total_amt"]].sum()

    item_df, item_source = await _load_dataset("item_master")
    log_fetch("most_profitable_skus", item_source, question)
    sku_col, wsp_col = ITEM_MASTER_COLS["sku_code"], ITEM_MASTER_COLS["wsp"]
    item_df[wsp_col] = pd.to_numeric(item_df[wsp_col], errors="coerce")
    cost = item_df.groupby(sku_col, as_index=False)[wsp_col].mean().rename(
        columns={sku_col: "SKU", wsp_col: "wsp"}
    )

    merged = revenue.merge(cost, on="SKU", how="inner")
    merged = merged.dropna(subset=["wsp"])
    merged["profit"] = merged["total_amt"] - (merged["wsp"] * merged["total_qty"])
    merged = merged.sort_values("profit", ascending=False).head(n)

    return {"days": days, "rows": merged.to_dict(orient="records")}


def format_most_profitable_skus(result: dict) -> str:
    rows = result["rows"]
    if not rows:
        return f"No profitability data found (last {result['days']} days)."
    lines = [f"💰 **Most profitable SKUs (last {result['days']} days, approx. — WSP used as cost):**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"{i}. **{row['SKU']}** — ₹{row['profit']:,.0f} est. profit ({int(row['total_qty'])} units)")
    return "\n".join(lines)


def _no_sale_streak_months(no_sale_series: pd.Series) -> int:
    streak = 0
    for v in reversed(no_sale_series.tolist()):
        if v:
            streak += 1
        else:
            break
    return streak


async def get_inventory_aging(n: int = 10, min_days: int = 60, question: str = "") -> dict:
    """Stores with the most stock that's been sitting with zero sales for at
    least `min_days` (approximated as consecutive no-sale months x 30, since
    the underlying data is monthly-grain)."""
    df, source = await _load_dataset("soh_monthly")
    log_fetch("inventory_aging", source, question)

    df = df.sort_values(["Site", "SKU", "Year", "Month"]).copy()
    df["no_sale"] = (df["sales"] == 0) & (df["soh"] > 0)

    streaks = (
        df.groupby(["Site", "SKU"])["no_sale"]
        .apply(_no_sale_streak_months)
        .reset_index(name="streak_months")
    )
    streaks["aging_days"] = streaks["streak_months"] * 30

    year, month = _latest_period(df)
    latest_soh = df[(df["Year"] == year) & (df["Month"] == month)][["Site", "SKU", "soh"]]
    aged = streaks.merge(latest_soh, on=["Site", "SKU"], how="inner")
    aged = aged[aged["aging_days"] >= min_days]

    by_store = aged.groupby("Site", as_index=False).agg(
        aged_sku_count=("SKU", "nunique"), total_aged_soh=("soh", "sum")
    ).sort_values("total_aged_soh", ascending=False).head(n)

    return {
        "period": f"{year}-{month:02d}",
        "min_days": min_days,
        "rows": by_store.to_dict(orient="records"),
    }


def format_inventory_aging(result: dict) -> str:
    rows = result["rows"]
    if not rows:
        return f"No inventory aging beyond {result['min_days']} days found."
    lines = [f"🕰️ **Highest inventory aging (>{result['min_days']} days, as of {result['period']}):**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(
            f"{i}. **{row['Site']}** — {int(row['total_aged_soh'])} units aged across {int(row['aged_sku_count'])} SKU(s)"
        )
    return "\n".join(lines)


async def get_return_rate(n: int = 10, group_by: str = "SKU", days: int = 30, question: str = "") -> dict:
    """Return rate = returned units / gross units sold, in the last `days`.
    Returns are inferred from negative total_qty rows in the sales export
    (a return recorded as a negative-quantity transaction). group_by='SKU' for
    highest-return products, 'Site' for return rate per store."""
    df, source = await _load_dataset("sales_export")
    log_fetch("return_rate", source, question)

    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
    max_date = df["Date"].max()
    window_df = df[df["Date"] >= max_date - pd.Timedelta(days=days)].copy()

    window_df["returns"] = window_df["total_qty"].clip(upper=0).abs()
    window_df["gross_sales"] = window_df["total_qty"].clip(lower=0)

    grouped = window_df.groupby(group_by, as_index=False)[["returns", "gross_sales"]].sum()
    grouped = grouped[grouped["gross_sales"] > 0]
    grouped["return_rate_pct"] = grouped["returns"] / grouped["gross_sales"] * 100
    grouped = grouped.sort_values("return_rate_pct", ascending=False).head(n)

    return {"days": days, "group_by": group_by, "rows": grouped.to_dict(orient="records")}


def format_return_rate(result: dict) -> str:
    rows = result["rows"]
    group_col = result["group_by"]
    if not rows:
        return f"No return data found (last {result['days']} days)."
    lines = [f"↩️ **Highest return rate by {group_col}, last {result['days']} days:**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(
            f"{i}. **{row[group_col]}** — {row['return_rate_pct']:.1f}% return rate "
            f"({int(row['returns'])} returned / {int(row['gross_sales'])} sold)"
        )
    return "\n".join(lines)


async def get_transfer_recommendations(
    n: int = 5, grades: tuple = ("A+", "1A+"), question: str = ""
) -> list[dict]:
    """Pending stock-transfer recommendations (0/low stock at receiver, donor
    store has it) restricted to donor stores graded in `grades`, highest
    priority_score first."""
    df, source = await _load_dataset("transfer_recommendations")
    log_fetch("transfer_recommendations", source, question)

    df = df[
        (df["donor_store_grade"].isin(grades))
        & (df["status"] == "PENDING")
        & (df["transfer_qty"] > 0)
    ]
    df = df.sort_values("priority_score", ascending=False).head(n)

    cols = [
        "receiver_site_name", "receiver_site_id", "receiver_city", "receiver_store_grade",
        "donor_site_name", "donor_site_id", "donor_city", "donor_store_grade",
        "sku", "size", "transfer_qty", "receiver_soh", "donor_soh",
        "priority_score", "created_at",
    ]
    result = df[cols].fillna("N/A").to_dict(orient="records")
    return result


def format_transfer_recommendations(rows: list[dict]) -> str:
    if not rows:
        return "There are no pending transfer recommendations right now (A+/1A+ donor stores)."

    lines = ["🔔 **Stock transfer recommendations (A+/1A+ donor stores):**\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(
            f"{i}. **{row['sku']} ({row['size']})** — {row['donor_site_name']} "
            f"[{row['donor_store_grade']}] → {row['receiver_site_name']} "
            f"[{row['receiver_store_grade']}], {int(row['transfer_qty'])} units"
        )
    return "\n".join(lines)
