"""Chat messages shown when user taps a card action (messageBack displayText)."""

from __future__ import annotations

# What appears in chat as if the user typed it
USER_MESSAGES: dict[str, str] = {
    "show_welcome": "Open StockPulse menu",
    "show_alerts_summary": "Show today's stock alerts",
    "refresh_summary": "Refresh stock alerts",
    "show_critical": "Show critical alerts",
    "show_medium": "Show medium alerts",
    "show_low": "Show low priority alerts",
    "show_by_store": "Show alerts by store",
    "show_inventory_summary": "Show inventory summary",
    "show_dead_stock": "Show dead stock",
    "show_top_skus": "Show top selling SKUs",
    "review_store": "View store alerts",
    "open_transfers": "Open transfer recommendations",
    "next_transfer": "Show next recommendation",
    "previous_transfer": "Show previous recommendation",
    "approve_transfer": "Approve this transfer",
    "reject_transfer": "Reject this transfer",
    "submit_reject": "Submit rejection reason",
    "dismiss_alert": "Dismiss alert",
    "show_critical_notification": "Show critical alert notification",
}

# Optional one-line bot reply before the card
BOT_REPLIES: dict[str, str] = {
    "show_alerts_summary": "Here's today's alert snapshot.",
    "refresh_summary": "Updated alert snapshot.",
    "show_critical": "Stores with critical alerts — tap **View Alerts** to drill in.",
    "show_medium": "Stores with medium-severity alerts.",
    "show_low": "Stores with low-severity alerts.",
    "show_by_store": "All stores with open alerts.",
    "review_store": "Store overview.",
    "open_transfers": "Transfer recommendations for this store.",
}


def user_message(verb: str, fallback: str = "") -> str:
    return USER_MESSAGES.get(verb, fallback or verb.replace("_", " ").title())
