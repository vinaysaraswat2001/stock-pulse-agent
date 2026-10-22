"""
Pydantic models for StockPulse Agent API contracts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentActionRequest(BaseModel):
    """POST /api/v1/agent/action — simulates Action.Execute from Teams."""

    verb: str = Field(..., description="Action.Execute verb, e.g. show_critical")
    data: dict[str, Any] = Field(default_factory=dict)
    user_id: str | None = Field(default=None, description="Teams user id (optional)")
    user_name: str | None = Field(default=None, description="Display name for approvals")


class AgentActionResponse(BaseModel):
    """Response containing the next Adaptive Card to render."""

    card_type: str
    card: dict[str, Any]
    message: str | None = None


class AlertSummaryDTO(BaseModel):
    date: str
    critical: int
    medium: int
    low: int
    total: int


class StoreSummaryDTO(BaseModel):
    id: str
    name: str
    city: str
    state: str
    critical: int
    medium: int
    low: int
    alertCount: int


class TransferDTO(BaseModel):
    id: str
    sku: str
    size: str
    requiredQty: int
    transferQty: int
    receiverSoh: int
    donorSoh: int
    donorStore: str
    donorGrade: str
    receiverGrade: str
    scope: str
    status: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"
