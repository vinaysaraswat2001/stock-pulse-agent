"""
FastAPI routes for StockPulse Agent (test + future GPT integration).
"""

from __future__ import annotations

from fastapi import APIRouter

from agent.bot_handler import card_to_attachment
from agent.models import AgentActionRequest, AgentActionResponse
from agent.router import router as agent_router

agent_api = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@agent_api.post("/action", response_model=AgentActionResponse)
async def agent_action(body: AgentActionRequest) -> AgentActionResponse:
    """
    Simulate Teams Action.Execute without the Bot channel.
    Returns the next Adaptive Card JSON.
    """
    user_name = body.user_name or "API User"
    return await agent_router.handle(body.verb, body.data, user_name=user_name)


@agent_api.get("/welcome")
async def agent_welcome(userName: str = "there") -> AgentActionResponse:
    return await agent_router.handle("show_welcome", {}, user_name=userName)


@agent_api.get("/alerts/summary")
async def agent_alerts_summary() -> AgentActionResponse:
    return await agent_router.handle("show_alerts_summary", {})


@agent_api.get("/cards/{card_type}/preview")
async def preview_card_attachment(card_type: str, userName: str = "Harsh"):
    """Returns Bot Framework attachment wrapper for Adaptive Card Designer testing."""
    verb_map = {
        "welcome": "show_welcome",
        "summary": "show_alerts_summary",
        "critical": "show_critical",
        "notification": "show_critical_notification",
    }
    verb = verb_map.get(card_type, "show_welcome")
    data = {}
    if verb == "show_critical_notification":
        data = {"storeId": "store-delhi", "sku": "ABC123", "stockoutDays": 2}
    result = await agent_router.handle(verb, data, user_name=userName)
    attachment = card_to_attachment(result.card)
    return {
        "card_type": result.card_type,
        "attachment": {
            "contentType": attachment.content_type,
            "content": attachment.content,
        },
        "card": result.card,
    }
