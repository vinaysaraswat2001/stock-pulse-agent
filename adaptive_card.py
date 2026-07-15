from botbuilder.core import MessageFactory
from botbuilder.schema import Attachment


def build_approve_reject_card(fabric_result: dict):
    """
    Approve / Reject card — jab Fabric Agent change karna chahta ho
    """
    summary = fabric_result.get("summary", "Ek action execute hoga")
    details = fabric_result.get("details", "")
    job_id  = fabric_result.get("job_id", "")

    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {
                "type": "Container",
                "style": "warning",
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
                                        "text": "⚠️",
                                        "size": "Large"
                                    }
                                ]
                            },
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": "Approval Required",
                                        "weight": "Bolder",
                                        "size": "Large",
                                        "color": "Warning"
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                "type": "TextBlock",
                "text": "**Proposed Action:**",
                "weight": "Bolder",
                "spacing": "Medium"
            },
            {
                "type": "TextBlock",
                "text": summary,
                "wrap": True,
                "spacing": "Small"
            },
            *(
                [
                    {
                        "type": "TextBlock",
                        "text": "**Details:**",
                        "weight": "Bolder",
                        "spacing": "Medium"
                    },
                    {
                        "type": "TextBlock",
                        "text": details,
                        "wrap": True,
                        "spacing": "Small",
                        "color": "Accent"
                    }
                ] if details else []
            ),
            {
                "type": "TextBlock",
                "text": f"Job ID: `{job_id}`",
                "size": "Small",
                "color": "Good",
                "spacing": "Medium",
                "isSubtle": True
            }
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "✅ Approve",
                "style": "positive",
                "data": {
                    "action": "approve",
                    "job_id": job_id,
                    "summary": summary
                }
            },
            {
                "type": "Action.Submit",
                "title": "❌ Reject",
                "style": "destructive",
                "data": {
                    "action": "reject",
                    "job_id": job_id,
                    "summary": summary
                }
            }
        ]
    }

    attachment = Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card
    )
    return MessageFactory.attachment(attachment)


def build_transfer_card(plan: dict):
    """
    Approve / Reject card for a proposed stock transfer, computed from real
    Lakehouse sales/SOH data. Approve/Reject buttons carry the full plan so
    on_invoke_activity can execute the write without extra server-side state.
    """
    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {
                "type": "Container",
                "style": "warning",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "⚠️ Stock Transfer — Approval Required",
                        "weight": "Bolder",
                        "size": "Large",
                        "color": "Warning",
                        "wrap": True
                    }
                ]
            },
            {
                "type": "FactSet",
                "spacing": "Medium",
                "facts": [
                    {"title": "SKU", "value": plan["sku"]},
                    {"title": "From store", "value": plan["from_store"]},
                    {"title": "To store", "value": plan["to_store"]},
                    {"title": "Quantity", "value": str(plan["qty"])},
                    {"title": "Basis", "value": f"Dead stock at source, best sales at destination ({plan['period']})"}
                ]
            }
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "✅ Approve Transfer",
                "style": "positive",
                "data": {
                    "action": "approve",
                    "type": "stock_transfer",
                    "sku": plan["sku"],
                    "from_store": plan["from_store"],
                    "to_store": plan["to_store"],
                    "qty": plan["qty"]
                }
            },
            {
                "type": "Action.Submit",
                "title": "❌ Reject",
                "style": "destructive",
                "data": {
                    "action": "reject",
                    "type": "stock_transfer",
                    "sku": plan["sku"],
                    "from_store": plan["from_store"],
                    "to_store": plan["to_store"],
                    "qty": plan["qty"]
                }
            }
        ]
    }

    attachment = Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card
    )
    return MessageFactory.attachment(attachment)


def build_recommendation_card(rec: dict):
    """
    Approve / Reject card for a stock-transfer recommendation pulled from
    Tables/dbo/final_transfer_sizewise. Button data carries every field
    needed to (a) write the stock_transfers audit row and (b) mark the
    source recommendation row APPROVED/REJECTED — no server-side state.
    """
    payload = {
        "type": "transfer_recommendation",
        "sku": rec["sku"],
        "size": rec["size"],
        "receiver_site_name": rec["receiver_site_name"],
        "receiver_site_id": rec["receiver_site_id"],
        "donor_site_name": rec["donor_site_name"],
        "donor_site_id": rec["donor_site_id"],
        "transfer_qty": rec["transfer_qty"],
        "created_at": rec["created_at"],
    }

    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {
                "type": "Container",
                "style": "warning",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "🔔 Stock Transfer Recommendation",
                        "weight": "Bolder",
                        "size": "Large",
                        "color": "Warning",
                        "wrap": True
                    }
                ]
            },
            {
                "type": "FactSet",
                "spacing": "Medium",
                "facts": [
                    {"title": "SKU / Size", "value": f"{rec['sku']} / {rec['size']}"},
                    {"title": "Donor store", "value": f"{rec['donor_site_name']} [{rec['donor_store_grade']}]"},
                    {"title": "Receiver store", "value": f"{rec['receiver_site_name']} [{rec['receiver_store_grade']}]"},
                    {"title": "Quantity", "value": str(int(rec["transfer_qty"]))},
                    {"title": "Receiver stock", "value": str(rec["receiver_soh"])},
                    {"title": "Priority score", "value": str(rec["priority_score"])},
                ]
            }
        ],
        "actions": [
            {
                "type": "Action.Submit",
                "title": "✅ Approve Transfer",
                "style": "positive",
                "data": {**payload, "action": "approve"}
            },
            {
                "type": "Action.Submit",
                "title": "❌ Reject",
                "style": "destructive",
                "data": {**payload, "action": "reject"}
            }
        ]
    }

    attachment = Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card
    )
    return MessageFactory.attachment(attachment)


def build_result_card(fabric_result: dict):
    """
    Simple result card — direct answer from Fabric Agent
    """
    output = fabric_result.get("output", "No response received.")
    job_id = fabric_result.get("job_id", "")

    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {
                "type": "Container",
                "style": "good",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": "✅ Fabric Agent Response",
                        "weight": "Bolder",
                        "size": "Medium",
                        "color": "Good"
                    }
                ]
            },
            {
                "type": "TextBlock",
                "text": output,
                "wrap": True,
                "spacing": "Medium"
            },
            {
                "type": "TextBlock",
                "text": f"Job ID: `{job_id}`",
                "size": "Small",
                "isSubtle": True,
                "spacing": "Medium"
            }
        ]
    }

    attachment = Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card
    )
    return MessageFactory.attachment(attachment)
