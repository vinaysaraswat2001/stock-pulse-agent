"""
Conversation router — maps card actions to the next Adaptive Card.
"""

from __future__ import annotations

from typing import Any

from agent import card_factory as cards
from agent import data_service as data
from agent.models import AgentActionResponse


class AgentRouter:
    """Processes verbs and returns the next card. Conversation = navigation."""

    async def handle(
        self,
        verb: str,
        payload: dict[str, Any] | None = None,
        *,
        user_name: str = "User",
    ) -> AgentActionResponse:
        payload = payload or {}
        verb = (verb or "").strip().lower()

        if verb in ("show_welcome", "home", "start"):
            return self._welcome(user_name)

        if verb in ("show_alerts_summary", "refresh_summary"):
            return self._summary()

        if verb == "show_critical":
            return self._store_list(
                title="Critical Alerts",
                subtitle="Stores with critical alerts — tap View Alerts to drill in.",
                severity="critical",
                refresh_verb="show_critical",
            )

        if verb == "show_medium":
            return self._store_list(
                title="Medium Alerts",
                subtitle="Stores with medium-severity alerts.",
                severity="medium",
                refresh_verb="show_medium",
            )

        if verb == "show_low":
            return self._store_list(
                title="Low Alerts",
                subtitle="Stores with low-severity alerts.",
                severity="low",
                refresh_verb="show_low",
            )

        if verb == "show_by_store":
            stores = data.get_stores()
            return AgentActionResponse(
                card_type="store_list",
                card=cards.build_store_list_card(
                    title="Alerts By Store",
                    subtitle="All stores with open alerts.",
                    stores=stores,
                    refresh_verb="show_by_store",
                ),
            )

        if verb == "review_store":
            store_id = payload.get("storeId")
            store = data.get_store(store_id) if store_id else None
            if not store:
                return self._error("Store not found.", "show_alerts_summary")
            back_verb = payload.get("backVerb") or "show_alerts_summary"
            return AgentActionResponse(
                card_type="store_detail",
                card=cards.build_store_detail_card(store, back_verb=back_verb),
            )

        if verb == "open_transfers":
            return self._transfer(payload)

        if verb in ("next_transfer", "previous_transfer"):
            return self._transfer_nav(payload, verb)

        if verb == "approve_transfer":
            return await self._approve(payload, user_name)

        if verb == "reject_transfer":
            return self._reject_reason_form(payload)

        if verb == "submit_reject":
            return await self._submit_reject(payload, user_name)

        if verb == "show_critical_notification":
            return self._critical_notification(payload)

        if verb == "dismiss_alert":
            return AgentActionResponse(
                card_type="info",
                card=cards.build_info_card(
                    "Alert dismissed",
                    "This alert was dismissed. You can reopen it anytime from Critical Alerts.",
                    "show_critical",
                ),
            )

        if verb == "show_inventory_summary":
            return AgentActionResponse(
                card_type="info",
                card=cards.build_info_card(
                    "Inventory Summary",
                    "Inventory summary will be available in Phase 4 when Fabric is connected.",
                    "show_welcome",
                ),
            )

        if verb == "show_dead_stock":
            return AgentActionResponse(
                card_type="info",
                card=cards.build_info_card(
                    "Dead Stock",
                    "Dead stock insights will be powered by Fabric in Phase 4.",
                    "show_welcome",
                ),
            )

        if verb == "show_top_skus":
            return AgentActionResponse(
                card_type="info",
                card=cards.build_info_card(
                    "Top Selling SKUs",
                    "Top SKU rankings will be available in Phase 4.",
                    "show_welcome",
                ),
            )

        return self._error(f"Unknown action: {verb}", "show_welcome")

    def _welcome(self, user_name: str) -> AgentActionResponse:
        return AgentActionResponse(
            card_type="welcome",
            card=cards.build_welcome_card(user_name),
        )

    def _summary(self) -> AgentActionResponse:
        summary = data.get_summary()
        return AgentActionResponse(
            card_type="summary",
            card=cards.build_summary_card(summary),
        )

    def _store_list(
        self,
        *,
        title: str,
        subtitle: str,
        severity: str,
        refresh_verb: str | None = None,
    ) -> AgentActionResponse:
        stores = data.get_stores(severity)
        verb = refresh_verb or f"show_{severity}"
        return AgentActionResponse(
            card_type="critical_list" if severity == "critical" else "store_list",
            card=cards.build_store_list_card(
                title=title,
                subtitle=subtitle,
                stores=stores,
                refresh_verb=verb,
                highlight=severity,
            ),
        )

    def _transfer(self, payload: dict) -> AgentActionResponse:
        store_id = payload.get("storeId")
        index = int(payload.get("index", 0))
        store = data.get_store(store_id) if store_id else None
        if not store:
            return self._error("Store not found.", "show_alerts_summary")

        transfers = [t for t in data.get_transfers(store_id) if t["status"] == "PENDING"]
        if not transfers:
            return AgentActionResponse(
                card_type="info",
                card=cards.build_info_card(
                    "No Pending Transfers",
                    f"All transfers for {store['name']} are already decided.",
                    "review_store",
                ),
                message="No pending transfers",
            )

        index = max(0, min(index, len(transfers) - 1))
        transfer = transfers[index]
        return AgentActionResponse(
            card_type="transfer",
            card=cards.build_transfer_card(
                store=store,
                transfer=transfer,
                index=index,
                total=len(transfers),
            ),
        )

    def _transfer_nav(self, payload: dict, verb: str) -> AgentActionResponse:
        store_id = payload.get("storeId")
        index = int(payload.get("index", 0))
        transfers = [t for t in data.get_transfers(store_id) if t["status"] == "PENDING"]
        if not transfers:
            return self._transfer({"storeId": store_id, "index": 0})

        if verb == "next_transfer":
            if payload.get("holdIndex"):
                # After approve/reject the pending list shrank — keep index
                index = min(index, len(transfers) - 1)
            else:
                index = min(index + 1, len(transfers) - 1)
        else:
            index = max(index - 1, 0)

        return self._transfer({"storeId": store_id, "index": index})

    async def _approve(self, payload: dict, user_name: str) -> AgentActionResponse:
        store_id = payload.get("storeId")
        transfer_id = payload.get("transferId")
        index = int(payload.get("index", 0))

        store = data.get_store(store_id) if store_id else None
        transfer = data.get_transfer(store_id, transfer_id) if store_id and transfer_id else None
        if not store or not transfer:
            return self._error("Transfer not found.", "show_alerts_summary")
        if transfer["status"] != "PENDING":
            return AgentActionResponse(
                card_type="info",
                card=cards.build_info_card(
                    "Already Decided",
                    f"This transfer was already {transfer['status'].lower()}.",
                    "open_transfers",
                ),
            )

        data.update_transfer_status(transfer_id, "APPROVED")
        remaining = len([t for t in data.get_transfers(store_id) if t["status"] == "PENDING"])

        return AgentActionResponse(
            card_type="approved",
            card=cards.build_approved_card(
                store=store,
                transfer=transfer,
                approved_by=user_name,
                date_label=data.display_date_label(),
                index=index,
                remaining=remaining,
            ),
        )

    def _reject_reason_form(self, payload: dict) -> AgentActionResponse:
        store_id = payload.get("storeId")
        transfer_id = payload.get("transferId")
        index = int(payload.get("index", 0))
        store = data.get_store(store_id) if store_id else None
        transfer = data.get_transfer(store_id, transfer_id) if store_id and transfer_id else None
        if not store or not transfer:
            return self._error("Transfer not found.", "show_alerts_summary")

        return AgentActionResponse(
            card_type="reject_reason",
            card=cards.build_reject_reason_card(
                store=store,
                transfer=transfer,
                index=index,
            ),
        )

    async def _submit_reject(self, payload: dict, user_name: str) -> AgentActionResponse:
        store_id = payload.get("storeId")
        transfer_id = payload.get("transferId")
        index = int(payload.get("index", 0))
        reason = (payload.get("rejectReason") or payload.get("reason") or "Other").strip()

        store = data.get_store(store_id) if store_id else None
        transfer = data.get_transfer(store_id, transfer_id) if store_id and transfer_id else None
        if not store or not transfer:
            return self._error("Transfer not found.", "show_alerts_summary")
        if transfer["status"] != "PENDING":
            return AgentActionResponse(
                card_type="info",
                card=cards.build_info_card(
                    "Already Decided",
                    f"This transfer was already {transfer['status'].lower()}.",
                    "open_transfers",
                ),
            )

        data.update_transfer_status(transfer_id, "REJECTED")
        remaining = len([t for t in data.get_transfers(store_id) if t["status"] == "PENDING"])

        return AgentActionResponse(
            card_type="rejected",
            card=cards.build_rejected_card(
                store=store,
                transfer=transfer,
                rejected_by=user_name,
                reason=reason,
                date_label=data.display_date_label(),
                index=index,
                remaining=remaining,
            ),
        )

    def _critical_notification(self, payload: dict) -> AgentActionResponse:
        store_id = payload.get("storeId") or "store-delhi"
        store = data.get_store(store_id) or data.get_stores()[0]
        sku = payload.get("sku") or "ABC123"
        days = int(payload.get("stockoutDays", 2))
        return AgentActionResponse(
            card_type="critical_notification",
            card=cards.build_critical_notification_card(
                store_name=store["name"],
                store_id=store["id"],
                sku=sku,
                stockout_days=days,
            ),
        )

    def _error(self, message: str, back_verb: str) -> AgentActionResponse:
        return AgentActionResponse(
            card_type="error",
            card=cards.build_info_card("Something went wrong", message, back_verb),
            message=message,
        )


router = AgentRouter()
