# Registry of known Lakehouse data sources — query functions look datasets
# up here by name instead of hardcoding OneLake paths per function. Add new
# entries here first when wiring a new question type.

DATASETS = {
    "sales_export": {
        "path": "Files/output/date_groupby_sales_export",
        "type": "dir",
        "description": (
            "Per-transaction sales rows: Site, SKU, Season, Color, DEPARTMENT, "
            "Date, total_qty, total_amt, First_Purchase_Date, "
            "First_180_Days_Purchase_Qty, Days_From_Purchase"
        ),
    },
    "soh_monthly": {
        "path": "Files/output/soh_result_new9.csv",
        "type": "file",
        "description": (
            "Store+SKU+month stock-on-hand vs. sales: Site, SKU, Season, Year, "
            "Month, sales, purchase, first_sale_month, cum_purchase, cum_sales, "
            "opening_stock, total_stock, valid_sales, closing_stock, soh"
        ),
    },
    "soh_weekly_discount": {
        "path": "Files/output/soh_add_dataset.csv",
        "type": "file",
        "description": (
            "Store+SKU+week grain with discount/revenue/category: Site, SKU, "
            "Season, Year, Month, Week, weekly_qty, weekly_avg_discount, "
            "weekly_total_revenue, weekly_avg_selling_price, last_4_week_avg_qty, "
            "lag_1..lag_4, DEPARTMENT, Color, Fabric, SECTION, product_type, "
            "fit_type, type, occasion, Monthly_avg_department_sales_trend, "
            "Monthly_avg_department_sales_2yr, opening_stock, total_stock, "
            "closing_stock, soh"
        ),
    },
    "item_master": {
        "path": "Tables/dbo/item master updated",
        "type": "delta_table",
        "description": (
            "Product catalog, headerless CSV so columns are _c0.._c46. Known "
            "mapping: ICODE=_c1, BARCODE=_c2, SKU CODE=_c4, SIZE=_c6, "
            "DEPARTMENT=_c14, SIZE IN CM=_c33, HSN CODE=_c35, STD RATE=_c37, "
            "WSP=_c38, RSP=_c39, MRP=_c40, VENDOR NAME=_c41"
        ),
    },
    "transfer_recommendations": {
        "path": "Tables/dbo/final_transfer_sizewise",
        "type": "delta_table",
        "description": (
            "Size-level stock transfer recommendations (donor store -> receiver "
            "store with 0/low stock): receiver_site_name, receiver_city, "
            "receiver_state, receiver_store_grade, donor_site_name, donor_city, "
            "donor_state, donor_store_grade, sku, size, barcode, required_qty, "
            "transfer_qty, receiver_soh, donor_soh, priority_score, "
            "receiver_last_week_sales, receiver_sold_qty_35d, receiver_total_sales, "
            "donor_last_week_sales, donor_sold_qty_35d, donor_total_sales, "
            "city_match, state_match, other_state, round, status (PENDING/APPROVED/"
            "REJECTED), created_at, receiver_site_id, donor_site_id. No single "
            "unique key column — use receiver_site_id+donor_site_id+sku+size+"
            "created_at+transfer_qty as the composite match key for updates."
        ),
    },
}
