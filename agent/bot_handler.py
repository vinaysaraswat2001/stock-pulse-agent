"""
Bridge between Bot Framework and StockPulse Agent router.
Handles card button clicks as conversational chat turns.
"""

from __future__ import annotations

from typing import Any

from botbuilder.core import MessageFactory, TurnContext
from botbuilder.schema import Activity, ActivityTypes, Attachment, InvokeResponse

from agent.router import router
from agent.verb_messages import BOT_REPLIES

# Navigation / decisions that update the same card (no new chat spam)
IN_PLACE_VERBS = frozenset({
    "previous_transfer",
    "next_transfer",
    "approve_transfer",
    "reject_transfer",
    "submit_reject",
})


def card_to_attachment(card: dict[str, Any]) -> Attachment:
    return Attachment(
        content_type="application/vnd.microsoft.card.adaptive",
        content=card,
    )


def card_to_activity(card: dict[str, Any]) -> Activity:
    return MessageFactory.attachment(card_to_attachment(card))


def extract_execute_payload(value: dict | None) -> tuple[str, dict]:
    """Parse Action.Submit / Action.Execute payload from Teams."""
    if not value:
        return "", {}

    # Universal Actions: { "action": { "type": "Action.Execute", "verb": "...", "data": {...} } }
    action = value.get("action") if isinstance(value.get("action"), dict) else value
    verb = action.get("verb") or action.get("action") or value.get("verb") or ""
    data = action.get("data") if isinstance(action.get("data"), dict) else {}

    if not isinstance(data, dict):
        data = {}

    # Action.Submit flattens verb + inputs (e.g. rejectReason) at top level
    top_level = {
        k: v
        for k, v in value.items()
        if k not in ("verb", "action", "msteams", "data", "type", "id", "title")
    }
    if not data:
        data = dict(top_level)
    else:
        data = {**data, **top_level}

    # Legacy Action.Submit fallback: { "action": "show_critical", ... }
    if not verb and value.get("action") and isinstance(value.get("action"), str):
        verb = value["action"]
        data = {k: v for k, v in value.items() if k not in ("action", "msteams")}

    return str(verb).strip().lower(), data


async def send_card(turn_context: TurnContext, card: dict[str, Any]) -> None:
    await turn_context.send_activity(card_to_activity(card))


async def _replace_card_in_place(turn_context: TurnContext, card: dict[str, Any]) -> bool:
    """Update the existing bot message that holds this card (carousel slide)."""
    reply_to = turn_context.activity.reply_to_id
    if not reply_to:
        # Some mobile clients omit reply_to_id — fall back to channelData parent message
        channel = turn_context.activity.channel_data or {}
        if isinstance(channel, dict):
            reply_to = channel.get("legacy", {}).get("replyToId") if isinstance(channel.get("legacy"), dict) else None
            reply_to = reply_to or channel.get("replyToId")
    if not reply_to:
        return False

    await turn_context.update_activity(
        Activity(
            type=ActivityTypes.message,
            id=reply_to,
            attachments=[card_to_attachment(card)],
        )
    )
    return True


def _invoke_card_response(card: dict[str, Any]) -> InvokeResponse:
    return InvokeResponse(
        status=200,
        body={
            "statusCode": 200,
            "type": "application/vnd.microsoft.card.adaptive",
            "value": card,
        },
    )


async def handle_agent_action(turn_context: TurnContext, verb: str, data: dict) -> InvokeResponse | None:
    """
    Conversational actions → new chat message (messageBack).
    In-place actions (Prev/Next) → swap card content, no new messages.
    """
    user = turn_context.activity.from_property
    user_name = (user.name if user else None) or "User"

    in_place = bool(data.get("inPlace")) or verb in IN_PLACE_VERBS

    result = await router.handle(verb, data, user_name=user_name)
    card = result.card

    if in_place:
        if turn_context.activity.type == ActivityTypes.invoke:
            return _invoke_card_response(card)
        if await _replace_card_in_place(turn_context, card):
            return None
        await send_card(turn_context, card)
        return None

    reply = result.message or BOT_REPLIES.get(verb)
    if reply:
        await turn_context.send_activity(reply)

    await send_card(turn_context, card)

    if turn_context.activity.type == ActivityTypes.invoke:
        return InvokeResponse(status=200, body={"statusCode": 200})

    return None
