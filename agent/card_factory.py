"""
Adaptive Card factory — polished Teams Agent UI.
Schema 1.5 · Action.Execute · responsive via targetWidth (desktop grid / mobile stack).
"""

from __future__ import annotations

from typing import Any

from agent.verb_messages import user_message

# Responsive breakpoints — Teams picks one variant based on card width
TW_DESKTOP = "atLeast:standard"  # desktop + tablet landscape → grids
TW_MOBILE = "atMost:narrow"      # phone + narrow chat → stacked boxes


def _col(items: list, *, width: str = "stretch") -> dict:
    return {"type": "Column", "width": width, "items": items}


def _column_set(columns: list, *, spacing: str = "Medium") -> dict:
    return {"type": "ColumnSet", "spacing": spacing, "columns": columns}


def _responsive_layout(*, desktop: dict, mobile: dict) -> list[dict]:
    """Two variants — Teams shows desktop grid or mobile stack, never both."""
    return [
        {**desktop, "targetWidth": TW_DESKTOP},
        {**mobile, "targetWidth": TW_MOBILE},
    ]


def _kpi_row(tiles: list[dict], *, spacing: str = "Medium") -> list[dict]:
    """Desktop: KPI tiles in one row. Mobile: one tile per row."""
    desktop = _column_set([_col([tile]) for tile in tiles], spacing=spacing)
    mobile = {
        "type": "Container",
        "spacing": "None",
        "items": [
            _column_set([_col([tile])], spacing="Small") for tile in tiles
        ],
    }
    return _responsive_layout(desktop=desktop, mobile=mobile)


def _grid_rows(items: list[dict], *, columns: int = 2, spacing: str = "Medium") -> list[dict]:
    """Desktop: N-column grid. Mobile: single column of boxes."""
    desktop_rows: list[dict] = []
    for i in range(0, len(items), columns):
        row_items = items[i : i + columns]
        cols = [_col([item]) for item in row_items]
        while len(cols) < columns:
            cols.append(_col([]))
        desktop_rows.append(_column_set(cols, spacing=spacing))

    desktop = {"type": "Container", "spacing": "None", "items": desktop_rows}
    mobile = {
        "type": "Container",
        "spacing": "None",
        "items": [_column_set([_col([item])], spacing=spacing) for item in items],
    }
    return _responsive_layout(desktop=desktop, mobile=mobile)


def _submit(
    title: str,
    verb: str,
    data: dict | None = None,
    style: str | None = None,
    *,
    chat_message: str | None = None,
) -> dict:
    """Action.Submit with messageBack — user question appears in chat."""
    display = chat_message or user_message(verb, title)
    payload = {"verb": verb, **(data or {})}
    action: dict[str, Any] = {
        "type": "Action.Submit",
        "title": title,
        "data": {
            **payload,
            "msteams": {
                "type": "messageBack",
                "displayText": display,
                "text": display,
            },
        },
        "msTeams": {"feedback": {"hide": True}},
    }
    if style:
        action["style"] = style
    return action


def _slide(
    title: str,
    verb: str,
    data: dict | None = None,
    style: str | None = None,
    *,
    enabled: bool = True,
    hold_index: bool = False,
) -> dict:
    """In-card navigation — Action.Execute updates the card in place (mobile-safe)."""
    payload: dict[str, Any] = {"inPlace": True, **(data or {})}
    if hold_index:
        payload["holdIndex"] = True
    action: dict[str, Any] = {
        "type": "Action.Execute",
        "title": title,
        "verb": verb,
        "data": payload,
        "msTeams": {"feedback": {"hide": True}},
    }
    if style:
        action["style"] = style
    if not enabled:
        action["isEnabled"] = False
    return action


def _select(verb: str, data: dict | None = None, *, chat_message: str | None = None) -> dict:
    """Tap-to-open on containers — same conversational messageBack behavior."""
    display = chat_message or user_message(verb)
    return {
        "type": "Action.Submit",
        "data": {
            "verb": verb,
            **(data or {}),
            "msteams": {
                "type": "messageBack",
                "displayText": display,
                "text": display,
            },
        },
    }


def _card(*, body: list, actions: list | None = None) -> dict[str, Any]:
    card: dict[str, Any] = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "msteams": {"width": "Full", "feedback": {"hide": True}},
        "body": body,
    }
    if actions:
        card["actions"] = actions[:6]
    return card


def _icon_nav(
    *,
    back_verb: str | None = None,
    back_data: dict | None = None,
    refresh_verb: str | None = None,
    refresh_data: dict | None = None,
    home: bool = True,
) -> list[dict]:
    """Icon-only Back / Refresh / Home for card top-right."""
    actions: list[dict] = []
    if back_verb:
        actions.append(
            _submit("←", back_verb, back_data, chat_message=user_message(back_verb, "Back"))
        )
    if refresh_verb:
        actions.append(
            _submit(
                "↻",
                refresh_verb,
                refresh_data,
                chat_message=user_message(refresh_verb, "Refresh"),
            )
        )
    if home:
        actions.append(_submit("🏠", "show_welcome", chat_message="Open StockPulse menu"))
    return actions


def _header(
    title: str,
    subtitle: str = "",
    *,
    style: str = "accent",
    icon: str = "",
    back_verb: str | None = None,
    back_data: dict | None = None,
    refresh_verb: str | None = None,
    refresh_data: dict | None = None,
    home: bool = False,
) -> list[dict]:
    display = f"{icon}  {title}".strip() if icon else title
    title_items: list[dict] = [
        {
            "type": "TextBlock",
            "text": display,
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        }
    ]
    if subtitle:
        title_items.append(
            {
                "type": "TextBlock",
                "text": subtitle,
                "isSubtle": True,
                "spacing": "Small",
                "wrap": True,
            }
        )

    nav = _icon_nav(
        back_verb=back_verb,
        back_data=back_data,
        refresh_verb=refresh_verb,
        refresh_data=refresh_data,
        home=home,
    )
    base = {"type": "Container", "style": style, "bleed": True}
    if not nav:
        return [{**base, "items": title_items}]

    desktop = {
        **base,
        "items": [
            _column_set(
                [
                    _col(title_items),
                    {
                        "type": "Column",
                        "width": "auto",
                        "verticalContentAlignment": "Top",
                        "items": [{"type": "ActionSet", "actions": nav}],
                    },
                ]
            )
        ],
    }
    mobile = {
        **base,
        "items": title_items + [{"type": "ActionSet", "spacing": "Small", "actions": nav}],
    }
    return _responsive_layout(desktop=desktop, mobile=mobile)


def _divider() -> dict:
    return {"type": "TextBlock", "text": " ", "separator": True, "spacing": "Medium"}


def _kpi_tile(label: str, value: str, color: str = "Default", icon: str = "") -> dict:
    label_text = f"{icon} {label.upper()}".strip()
    return {
        "type": "Container",
        "style": "emphasis",
        "items": [
            {
                "type": "TextBlock",
                "text": label_text,
                "size": "Small",
                "isSubtle": True,
                "spacing": "None",
            },
            {
                "type": "TextBlock",
                "text": value,
                "size": "ExtraLarge",
                "weight": "Bolder",
                "color": color,
                "spacing": "Small",
            },
        ],
    }


def _menu_tile(
    icon: str,
    title: str,
    description: str,
    verb: str,
    data: dict | None = None,
    accent: str = "emphasis",
) -> dict:
    return {
        "type": "Container",
        "style": accent,
        "spacing": "Medium",
        "selectAction": _select(verb, data, chat_message=user_message(verb, title)),
        "items": [
            {
                "type": "ColumnSet",
                "columns": [
                    {
                        "type": "Column",
                        "width": "auto",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": icon,
                                "size": "ExtraLarge",
                                "spacing": "None",
                            }
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": title,
                                "weight": "Bolder",
                                "wrap": True,
                                "spacing": "None",
                            },
                            {
                                "type": "TextBlock",
                                "text": description,
                                "isSubtle": True,
                                "size": "Small",
                                "wrap": True,
                                "spacing": "Small",
                            },
                            {
                                "type": "TextBlock",
                                "text": "Tap to open →",
                                "size": "Small",
                                "color": "Accent",
                                "spacing": "Small",
                            },
                        ],
                    },
                ],
            }
        ],
    }


def build_welcome_card(user_name: str = "there") -> dict[str, Any]:
    first = user_name.split()[0] if user_name and user_name != "there" else "there"
    menu_items = [
        _menu_tile("🚨", "Stock Alerts", "Today's summary & drill-down", "show_alerts_summary", accent="attention"),
        _menu_tile("🔥", "Critical Alerts", "Stores needing urgent action", "show_critical", accent="attention"),
        _menu_tile("📊", "Inventory Summary", "High-level stock snapshot", "show_inventory_summary"),
        _menu_tile("📉", "Dead Stock", "Slow movers & clearance", "show_dead_stock"),
        _menu_tile("🏆", "Top Selling SKUs", "Best performers this period", "show_top_skus"),
    ]
    return _card(
        body=[
            *_header(
                "StockPulse AI",
                f"Hey {first} — inventory intelligence, right inside Teams.",
                icon="📦",
                refresh_verb="show_welcome",
            ),
            {
                "type": "TextBlock",
                "text": "No dashboards. Just tap a card and work through alerts step by step.",
                "wrap": True,
                "spacing": "Medium",
                "isSubtle": True,
            },
            *_grid_rows(menu_items, columns=2),
        ],
    )


def build_summary_card(summary: dict) -> dict[str, Any]:
    total = summary.get("total") or (summary["critical"] + summary["medium"] + summary["low"])
    kpis = [
        _kpi_tile("Critical", str(summary["critical"]), "Attention", "🔴"),
        _kpi_tile("Medium", str(summary["medium"]), "Warning", "🟠"),
        _kpi_tile("Low", str(summary["low"]), "Good", "🟢"),
    ]
    return _card(
        body=[
            *_header(
                "Today's Alerts",
                f"Snapshot · {summary.get('date', 'Today')}",
                icon="📋",
                refresh_verb="refresh_summary",
                home=True,
            ),
            *_kpi_row(kpis),
            {
                "type": "Container",
                "spacing": "Medium",
                "items": [_kpi_tile("Total open alerts", str(total), "Accent", "📦")],
            },
            _divider(),
            {
                "type": "TextBlock",
                "text": "Filter by severity",
                "weight": "Bolder",
                "spacing": "None",
            },
            {
                "type": "ActionSet",
                "actions": [
                    _submit("🔴 Critical", "show_critical"),
                    _submit("🟠 Medium", "show_medium"),
                    _submit("🟢 Low", "show_low"),
                    _submit("🏪 By Store", "show_by_store"),
                ],
            },
        ],
    )


def build_store_list_card(
    *,
    title: str,
    subtitle: str,
    stores: list[dict],
    back_verb: str = "show_alerts_summary",
    refresh_verb: str | None = None,
    highlight: str | None = None,
) -> dict[str, Any]:
    body: list[dict] = [
        *_header(
            title,
            subtitle,
            icon="🏪",
            back_verb=back_verb,
            refresh_verb=refresh_verb or back_verb,
            home=True,
        ),
    ]

    if not stores:
        body.append(
            {
                "type": "Container",
                "style": "warning",
                "items": [
                    {"type": "TextBlock", "text": "✨ No stores match this filter.", "wrap": True},
                ],
            }
        )
        return _card(body=body)

    def _store_tile(store: dict) -> dict:
        store_msg = f"View alerts for {store['name']}"
        review_data = {"storeId": store["id"], "backVerb": refresh_verb or back_verb}
        return {
            "type": "Container",
            "style": "emphasis",
            "selectAction": _select("review_store", review_data, chat_message=store_msg),
            "items": [
                {
                    "type": "TextBlock",
                    "text": store["name"],
                    "weight": "Bolder",
                    "size": "Medium",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": f"Total alerts :- **{store['alertCount']}**",
                    "spacing": "Small",
                    "wrap": True,
                },
                {
                    "type": "ActionSet",
                    "spacing": "Small",
                    "actions": [
                        _submit(
                            "View Alerts →",
                            "review_store",
                            review_data,
                            style="positive",
                            chat_message=store_msg,
                        ),
                    ],
                },
            ],
        }

    store_tiles = [_store_tile(store) for store in stores]
    body.extend(_grid_rows(store_tiles, columns=2))

    return _card(body=body)


def build_store_detail_card(store: dict, *, back_verb: str = "show_alerts_summary") -> dict[str, Any]:
    open_msg = f"Open transfers for {store['name']}"
    refresh_data = {"storeId": store["id"], "backVerb": back_verb}
    kpis = [
        _kpi_tile("Total", str(store["alertCount"]), "Accent", "📦"),
        _kpi_tile("Critical", str(store["critical"]), "Attention", "🔴"),
        _kpi_tile("Medium", str(store["medium"]), "Warning", "🟠"),
        _kpi_tile("Low", str(store["low"]), "Good", "🟢"),
    ]
    return _card(
        body=[
            *_header(
                store["name"],
                f"{store.get('city', '')} · Store overview",
                icon="🏬",
                back_verb=back_verb,
                refresh_verb="review_store",
                refresh_data=refresh_data,
                home=True,
            ),
            *_kpi_row(kpis, spacing="Small"),
            {
                "type": "ActionSet",
                "spacing": "Medium",
                "actions": [
                    _submit(
                        "📦 Open Transfers",
                        "open_transfers",
                        {"storeId": store["id"], "index": 0, "backVerb": back_verb},
                        style="positive",
                        chat_message=open_msg,
                    ),
                ],
            },
        ],
    )


def build_transfer_card(
    *,
    store: dict,
    transfer: dict,
    index: int,
    total: int,
) -> dict[str, Any]:
    data = {"transferId": transfer["id"], "storeId": store["id"], "index": index}
    grade = transfer.get("donorGrade", "-")

    product_block = {
        "type": "Container",
        "style": "emphasis",
        "items": [
            {"type": "TextBlock", "text": "Product", "weight": "Bolder", "size": "Small", "isSubtle": True, "wrap": True},
            {"type": "TextBlock", "text": transfer["sku"], "weight": "Bolder", "size": "Medium", "spacing": "None", "wrap": True},
            {"type": "TextBlock", "text": f"Size {transfer['size']}", "spacing": "None", "wrap": True},
        ],
    }
    donor_block = {
        "type": "Container",
        "style": "emphasis",
        "items": [
            {"type": "TextBlock", "text": "Donor Store", "weight": "Bolder", "size": "Small", "isSubtle": True, "wrap": True},
            {"type": "TextBlock", "text": transfer["donorStore"], "weight": "Bolder", "wrap": True, "spacing": "None"},
            {"type": "TextBlock", "text": f"Grade {grade}", "spacing": "None", "wrap": True},
        ],
    }
    product_donor = _responsive_layout(
        desktop=_column_set([_col([product_block]), _col([donor_block])]),
        mobile={
            "type": "Container",
            "spacing": "None",
            "items": [product_block, donor_block],
        },
    )
    stock_kpis = _kpi_row([
        _kpi_tile("Recv. Stock", f"{transfer['receiverSoh']} Units", "Attention", "📦"),
        _kpi_tile("Transfer", f"{transfer['transferQty']} Units", "Accent", "🚚"),
    ])

    return _card(
        body=[
            *_header(
                "Transfer Recommendation",
                f"{store['name']} · {index + 1} of {total}",
                icon="🔄",
                back_verb="review_store",
                back_data={"storeId": store["id"]},
                refresh_verb="open_transfers",
                refresh_data={"storeId": store["id"], "index": index},
                home=True,
            ),
            *product_donor,
            *stock_kpis,
            {
                "type": "TextBlock",
                "text": f"Required: **{transfer['requiredQty']}** · Donor: **{transfer['donorSoh']}** units",
                "isSubtle": True,
                "wrap": True,
                "spacing": "Small",
            },
            {
                "type": "ActionSet",
                "spacing": "Medium",
                "actions": [
                    _slide("← Prev", "previous_transfer", {"storeId": store["id"], "index": index}, enabled=index > 0),
                    _slide("Next →", "next_transfer", {"storeId": store["id"], "index": index}, enabled=index < total - 1),
                ],
            },
        ],
        actions=[
            _slide("✓ Approve", "approve_transfer", data, style="positive"),
            _slide("✗ Reject", "reject_transfer", data, style="destructive"),
        ],
    )


def build_approved_card(
    *,
    store: dict,
    transfer: dict,
    approved_by: str,
    date_label: str,
    index: int,
    remaining: int,
) -> dict[str, Any]:
    """In-place card after Approve — Approve button gone, Next Recommendation shown."""
    next_actions = []
    if remaining > 0:
        next_actions.append(
            _slide(
                "Next Recommendation →",
                "next_transfer",
                {"storeId": store["id"], "index": index},
                style="positive",
                hold_index=True,
            )
        )
    else:
        next_actions.append(
            _submit("All alerts", "show_alerts_summary", chat_message="Show today's stock alerts")
        )

    return _card(
        body=[
            *_header("✅ Approved", store["name"], style="good", home=True),
            {
                "type": "FactSet",
                "spacing": "Medium",
                "facts": [
                    {"title": "Product", "value": f"{transfer['sku']} · Size {transfer['size']}"},
                    {"title": "Transfer", "value": f"{transfer['transferQty']} Units"},
                    {"title": "Approved by", "value": approved_by},
                    {"title": "Date", "value": date_label},
                ],
            },
            {
                "type": "ActionSet",
                "spacing": "Medium",
                "actions": next_actions,
            },
        ],
    )


def build_reject_reason_card(
    *,
    store: dict,
    transfer: dict,
    index: int,
) -> dict[str, Any]:
    data = {"transferId": transfer["id"], "storeId": store["id"], "index": index}
    return _card(
        body=[
            *_header(
                "Reject Transfer",
                f"{store['name']} · {transfer['sku']} Size {transfer['size']}",
                style="attention",
                icon="✗",
                back_verb="open_transfers",
                back_data={"storeId": store["id"], "index": index},
                home=True,
            ),
            {
                "type": "TextBlock",
                "text": "Reason",
                "weight": "Bolder",
                "spacing": "Medium",
            },
            {
                "type": "Input.ChoiceSet",
                "id": "rejectReason",
                "style": "expanded",
                "isRequired": True,
                "value": "Out of Stock",
                "choices": [
                    {"title": "Out of Stock", "value": "Out of Stock"},
                    {"title": "Capacity Issue", "value": "Capacity Issue"},
                    {"title": "Other", "value": "Other"},
                ],
            },
        ],
        actions=[
            _slide("Submit", "submit_reject", data, style="destructive"),
            _slide("Cancel", "open_transfers", {"storeId": store["id"], "index": index}),
        ],
    )


def build_rejected_card(
    *,
    store: dict,
    transfer: dict,
    rejected_by: str,
    reason: str,
    date_label: str,
    index: int,
    remaining: int,
) -> dict[str, Any]:
    next_actions = []
    if remaining > 0:
        next_actions.append(
            _slide(
                "Next Recommendation →",
                "next_transfer",
                {"storeId": store["id"], "index": index},
                style="positive",
                hold_index=True,
            )
        )
    else:
        next_actions.append(
            _submit("All alerts", "show_alerts_summary", chat_message="Show today's stock alerts")
        )

    return _card(
        body=[
            *_header("❌ Rejected", store["name"], style="attention", home=True),
            {
                "type": "FactSet",
                "spacing": "Medium",
                "facts": [
                    {"title": "Product", "value": f"{transfer['sku']} · Size {transfer['size']}"},
                    {"title": "Transfer", "value": f"{transfer['transferQty']} Units"},
                    {"title": "Reason", "value": reason},
                    {"title": "Rejected by", "value": rejected_by},
                    {"title": "Date", "value": date_label},
                ],
            },
            {
                "type": "ActionSet",
                "spacing": "Medium",
                "actions": next_actions,
            },
        ],
    )


def build_critical_notification_card(
    *,
    store_name: str,
    store_id: str,
    sku: str,
    stockout_days: int = 2,
) -> dict[str, Any]:
    """Compact real-time push card — no dashboard dump."""
    return _card(
        body=[
            *_header("🚨 Critical Alert", "Immediate attention needed", style="attention"),
            {
                "type": "FactSet",
                "spacing": "Medium",
                "facts": [
                    {"title": "Store", "value": store_name},
                    {"title": "SKU", "value": sku},
                    {"title": "Stockout in", "value": f"{stockout_days} Days"},
                ],
            },
        ],
        actions=[
            _submit(
                "View Alert",
                "review_store",
                {"storeId": store_id, "backVerb": "show_critical"},
                style="positive",
                chat_message=f"View alert for {store_name}",
            ),
            _submit("Dismiss", "dismiss_alert", chat_message="Dismiss alert"),
        ],
    )


def build_info_card(title: str, message: str, back_verb: str = "show_welcome") -> dict[str, Any]:
    return _card(
        body=[
            *_header(
                title,
                message,
                style="emphasis",
                icon="ℹ️",
                back_verb=back_verb,
                home=True,
            ),
        ],
    )
