import re
from botbuilder.core import ActivityHandler, TurnContext, MessageFactory
from botbuilder.schema import ActivityTypes, Activity
from fabric_client import trigger_fabric_agent, execute_fabric_action
from adaptive_card import build_approve_reject_card, build_result_card, build_transfer_card
from sales_query import (
    get_top_skus, format_top_skus,
    get_top_stores, format_top_stores,
    get_dead_stock, format_dead_stock,
    get_sku_count,
    get_transfer_plan,
)
from lakehouse_client import record_stock_transfer
import json

SKU_PATTERN = re.compile(r"\b[A-Za-z]{1,3}\d{4,6}\b")


class StockpulseBot(ActivityHandler):

    # ─────────────────────────────────────────────
    # User joins the chat
    # ─────────────────────────────────────────────
    async def on_members_added_activity(self, members_added, turn_context: TurnContext):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    "👋 **Stockpulse Bot** ready hai!\n\n"
                    "Mujhse Fabric Agent ke baare mein kuch bhi pucho ya "
                    "pipeline trigger karne ke liye bolo."
                )

    # ─────────────────────────────────────────────
    # User sends a message
    # ─────────────────────────────────────────────
    async def on_message_activity(self, turn_context: TurnContext):
        # Adaptive Card Action.Submit clicks (Approve/Reject buttons) arrive as a
        # message activity with empty text but a populated `value` — not as an
        # Invoke activity — so they must be caught here, before the empty-text check.
        if turn_context.activity.value:
            await self._handle_card_action(turn_context, turn_context.activity.value)
            return

        user_message = turn_context.activity.text

        if not user_message:
            await turn_context.send_activity("Kuch message bhejo bhai! 😅")
            return

        # Typing indicator
        await turn_context.send_activity(Activity(type=ActivityTypes.typing))

        try:
            lower_msg = user_message.lower()

            if "transfer" in lower_msg and SKU_PATTERN.search(user_message):
                sku = SKU_PATTERN.search(user_message).group(0).upper()
                plan = await get_transfer_plan(sku, question=user_message)

                if not plan:
                    await turn_context.send_activity(
                        f"ℹ️ {sku} ke liye koi dead stock transfer nahi mila "
                        f"(ya toh dead stock hai hi nahi, ya already best-selling store me hai)."
                    )
                    return

                card_activity = build_transfer_card(plan)
                await turn_context.send_activity(card_activity)
                return

            if "how many sku" in lower_msg or "how many skus" in lower_msg or "sku count" in lower_msg:
                count = await get_sku_count(question=user_message)
                fabric_result = {
                    "requires_approval": False,
                    "output": f"📦 Total **{count}** unique SKUs sales data me hain.",
                    "job_id": "sales_query"
                }
            elif "top sku" in lower_msg:
                # Real sales data se seedha answer nikaalo — notebook/agent skip
                rows = await get_top_skus(n=10, by="qty", question=user_message)
                fabric_result = {
                    "requires_approval": False,
                    "output": format_top_skus(rows),
                    "job_id": "sales_query"
                }
            elif "dead stock" in lower_msg or "deadstock" in lower_msg:
                result = await get_dead_stock(n=10, question=user_message)
                fabric_result = {
                    "requires_approval": False,
                    "output": format_dead_stock(result),
                    "job_id": "sales_query"
                }
            elif "store" in lower_msg and ("best" in lower_msg or "perform" in lower_msg or "top" in lower_msg):
                rows = await get_top_stores(n=10, by="amt", question=user_message)
                fabric_result = {
                    "requires_approval": False,
                    "output": format_top_stores(rows),
                    "job_id": "sales_query"
                }
            else:
                # Notebook run karo, phir Lakehouse se real output fetch karo
                fabric_result = await trigger_fabric_agent(user_message)

            # Agar approval chahiye (change/update/delete request)
            if fabric_result.get("requires_approval"):
                card_activity = build_approve_reject_card(fabric_result)
                await turn_context.send_activity(card_activity)

            else:
                # Direct result card
                result_activity = build_result_card(fabric_result)
                await turn_context.send_activity(result_activity)

        except Exception as e:
            print(f"[BOT ERROR] {e}")
            await turn_context.send_activity(
                f"❌ Fabric Agent se response nahi mila.\n\nError: `{str(e)}`"
            )

    # ─────────────────────────────────────────────
    # Approve / Reject button click handler
    # Teams delivers Action.Submit as a message activity (handled in
    # on_message_activity above); some channels (e.g. Web Chat) may still
    # deliver it as a true Invoke activity, so both paths call this.
    # ─────────────────────────────────────────────
    async def on_invoke_activity(self, turn_context: TurnContext):
        value = turn_context.activity.value or {}
        await self._handle_card_action(turn_context, value)

    async def _handle_card_action(self, turn_context: TurnContext, value: dict):
        action = value.get("action")

        if not action:
            await turn_context.send_activity("⚠️ Card se koi valid action nahi mila.")
            return

        await turn_context.send_activity(Activity(type=ActivityTypes.typing))

        # Stock transfer Approve/Reject — writes to Tables/dbo/stock_transfers
        if value.get("type") == "stock_transfer":
            sku = value.get("sku")
            from_store = value.get("from_store")
            to_store = value.get("to_store")
            qty = value.get("qty")

            if action == "approve":
                requester = turn_context.activity.from_property.name or "teams_user"
                row = await record_stock_transfer(sku, from_store, to_store, qty, decided_by=requester)
                await turn_context.send_activity(
                    f"✅ **Transfer approved and logged.**\n\n"
                    f"**{qty} units of {sku}** — {from_store} → {to_store}\n"
                    f"Transfer ID: `{row['transfer_id']}`"
                )
            elif action == "reject":
                await turn_context.send_activity(
                    f"👍 Understood — this transfer request has been rejected.\n\n"
                    f"**{qty} units of {sku}** — {from_store} → {to_store}\n"
                    f"No changes were made to your stock."
                )
            else:
                await turn_context.send_activity("⚠️ Unrecognized action on this card.")
            return

        job_id = value.get("job_id")
        summary = value.get("summary", "")

        if not job_id:
            await turn_context.send_activity("⚠️ Card se koi valid action nahi mila.")
            return

        if action == "approve":
            result = await execute_fabric_action(job_id, approved=True)
            await turn_context.send_activity(
                f"✅ **Approved.**\n\n"
                f"**Action:** {summary}\n"
                f"**Status:** Pipeline execute ho raha hai...\n"
                f"**Job ID:** `{job_id}`"
            )

        elif action == "reject":
            await execute_fabric_action(job_id, approved=False)
            await turn_context.send_activity(
                f"👍 Understood — this request has been rejected.\n\n"
                f"**Action:** {summary}\n"
                f"No changes were made."
            )

        else:
            await turn_context.send_activity("⚠️ Unrecognized action on this card.")
