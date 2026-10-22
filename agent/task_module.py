"""
Teams Task Module (Dialog) helpers for StockPulse Agent.

Adaptive Card → View Alerts → task/fetch → React dialog popup.
"""

from __future__ import annotations

import os
from typing import Any

from botbuilder.schema import InvokeResponse

from agent import data_service as data


def dialog_base_url() -> str:
    """Public URL of the Vite frontend (dev tunnel / ngrok)."""
    return (os.getenv("DIALOG_BASE_URL") or "http://localhost:5173").rstrip("/")


def dialog_url(path: str = "/dialog") -> str:
    """
    Public dialog URL for Teams Task Module.

    Use ?view=dialog (not #/dialog) — Teams iframes often strip hash fragments,
    which leaves a blank white dialog.
    """
    base = dialog_base_url()
    return f"{base}/?view=dialog"


def build_compact_summary_card(summary: dict | None = None) -> dict[str, Any]:
    """Compact chat card — summary + View Alerts opens Teams Dialog."""
    summary = summary or data.get_summary()
    total = summary.get("total") or (
        summary["critical"] + summary["medium"] + summary["low"]
    )

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "msteams": {"width": "Full", "feedback": {"hide": True}},
        "body": [
            {
                "type": "Container",
                "style": "accent",
                "bleed": True,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "📋  Stock Alerts",
                        "weight": "Bolder",
                        "size": "Large",
                        "wrap": True,
                    },
                    {
                        "type": "TextBlock",
                        "text": f"Snapshot · {summary.get('date', 'Today')}",
                        "isSubtle": True,
                        "spacing": "Small",
                        "wrap": True,
                    },
                ],
            },
            {
                "type": "ColumnSet",
                "spacing": "Medium",
                "columns": [
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": "CRITICAL",
                                "size": "Small",
                                "isSubtle": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": str(summary["critical"]),
                                "size": "ExtraLarge",
                                "weight": "Bolder",
                                "color": "Attention",
                            },
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": "MEDIUM",
                                "size": "Small",
                                "isSubtle": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": str(summary["medium"]),
                                "size": "ExtraLarge",
                                "weight": "Bolder",
                                "color": "Warning",
                            },
                        ],
                    },
                    {
                        "type": "Column",
                        "width": "stretch",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": "LOW",
                                "size": "Small",
                                "isSubtle": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": str(summary["low"]),
                                "size": "ExtraLarge",
                                "weight": "Bolder",
                                "color": "Good",
                            },
                        ],
                    },
                ],
            },
            {
                "type": "TextBlock",
                "text": f"**{total}** open alerts across your network",
                "wrap": True,
                "spacing": "Medium",
            },
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "View Alerts",
                "data": {"msteams": {"type": "task/fetch"}},
                "msTeams": {"feedback": {"hide": True}},
            },
        ],
    }


def task_fetch_response(*, title: str = "Stock Alerts") -> InvokeResponse:
    url = dialog_url("dialog")
    return InvokeResponse(
        status=200,
        body={
            "task": {
                "type": "continue",
                "value": {
                    "title": title,
                    "height": 620,
                    "width": 720,
                    "url": url,
                    "fallbackUrl": url,
                },
            }
        },
    )


def task_submit_response(result: dict | None = None) -> InvokeResponse:
    """Acknowledge dialog close — optional message back to chat."""
    payload = result or {}
    status = payload.get("status", "closed")
    message = payload.get("message") or f"Dialog closed ({status})."

    return InvokeResponse(
        status=200,
        body={
            "task": {
                "type": "message",
                "value": message,
            }
        },
    )
