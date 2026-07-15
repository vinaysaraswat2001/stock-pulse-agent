import re
from botbuilder.core import ActivityHandler, TurnContext, MessageFactory
from botbuilder.schema import ActivityTypes, Activity
from fabric_client import trigger_fabric_agent, execute_fabric_action
from adaptive_card import build_approve_reject_card, build_result_card, build_transfer_card, build_recommendation_card
from sales_query import (
    get_top_skus, format_top_skus,
    get_top_stores, format_top_stores,
    get_dead_stock, format_dead_stock,
    get_dead_stock_totals, format_dead_stock_totals,
    get_sku_count,
    get_transfer_plan,
    get_sell_through_rate, format_sell_through_rate,
    get_department_discount_stats, format_lowest_discount_categories, format_avg_discount_by_department,
    get_below_average_sales, format_below_average_sales,
    get_stockouts, format_stockouts,
    get_markdown_candidates, format_markdown_candidates,
    get_stock_coverage_days, format_stock_coverage_days,
    get_purchase_sales_gap, format_purchase_sales_gap,
    get_overstocked_products, format_overstocked_products,
    get_full_price_sales_by_store, format_full_price_sales_by_store,
    get_sku_contribution, format_sku_contribution,
    get_most_profitable_skus, format_most_profitable_skus,
    get_inventory_aging, format_inventory_aging,
    get_return_rate, format_return_rate,
    get_transfer_recommendations, format_transfer_recommendations,
)
from lakehouse_client import record_stock_transfer, update_recommendation_status
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
                    "👋 **Welcome to Stockpulse Bot.**\n\n"
                    "Ask me about sales, inventory, stock transfers, or store performance — "
                    "for example, *\"top selling skus\"*, *\"dead stock\"*, or *\"show me recommendations\"*."
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
            await turn_context.send_activity("Please send a message so I can help.")
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
                        f"ℹ️ No transfer opportunity found for {sku} — "
                        f"either there's no dead stock for it, or it's already at its best-selling store."
                    )
                    return

                card_activity = build_transfer_card(plan)
                await turn_context.send_activity(card_activity)
                return

            if "recommendation" in lower_msg or "stock alert" in lower_msg or "transfer alert" in lower_msg:
                recs = await get_transfer_recommendations(n=5, question=user_message)

                if not recs:
                    await turn_context.send_activity(
                        "ℹ️ There are no pending transfer recommendations right now (A+/1A+ donor stores)."
                    )
                    return

                for rec in recs:
                    card_activity = build_recommendation_card(rec)
                    await turn_context.send_activity(card_activity)
                return

            if "how many sku" in lower_msg or "how many skus" in lower_msg or "sku count" in lower_msg:
                count = await get_sku_count(question=user_message)
                fabric_result = {
                    "requires_approval": False,
                    "output": f"📦 There are **{count}** unique SKUs in the sales data.",
                    "job_id": "sales_query"
                }
            elif "sell through" in lower_msg or "sell-through" in lower_msg or "sellthrough" in lower_msg:
                result = await get_sell_through_rate(n=10, question=user_message)
                fabric_result = {"requires_approval": False, "output": format_sell_through_rate(result), "job_id": "sales_query"}
            elif "dead stock" in lower_msg and ("total" in lower_msg or "by sku" in lower_msg):
                result = await get_dead_stock_totals(n=10, question=user_message)
                fabric_result = {"requires_approval": False, "output": format_dead_stock_totals(result), "job_id": "sales_query"}
            elif "dead stock" in lower_msg or "deadstock" in lower_msg:
                result = await get_dead_stock(n=10, question=user_message)
                fabric_result = {
                    "requires_approval": False,
                    "output": format_dead_stock(result),
                    "job_id": "sales_query"
                }
            elif "lowest discount" in lower_msg:
                rows = await get_department_discount_stats(question=user_message)
                fabric_result = {"requires_approval": False, "output": format_lowest_discount_categories(rows), "job_id": "sales_query"}
            elif "discount" in lower_msg and ("department" in lower_msg or "category" in lower_msg or "categories" in lower_msg or "average" in lower_msg or "avg" in lower_msg):
                rows = await get_department_discount_stats(question=user_message)
                fabric_result = {"requires_approval": False, "output": format_avg_discount_by_department(rows), "job_id": "sales_query"}
            elif "below average" in lower_msg or "below-average" in lower_msg:
                result = await get_below_average_sales(n=10, question=user_message)
                fabric_result = {"requires_approval": False, "output": format_below_average_sales(result), "job_id": "sales_query"}
            elif "stockout" in lower_msg or "stock out" in lower_msg or "out of stock" in lower_msg:
                result = await get_stockouts(n=10, question=user_message)
                fabric_result = {"requires_approval": False, "output": format_stockouts(result), "job_id": "sales_query"}
            elif "markdown" in lower_msg:
                result = await get_markdown_candidates(n=10, question=user_message)
                fabric_result = {"requires_approval": False, "output": format_markdown_candidates(result), "job_id": "sales_query"}
            elif "coverage" in lower_msg:
                rows = await get_stock_coverage_days(n=10, question=user_message)
                fabric_result = {"requires_approval": False, "output": format_stock_coverage_days(rows), "job_id": "sales_query"}
            elif "gap" in lower_msg and ("purchase" in lower_msg or "sales" in lower_msg):
                result = await get_purchase_sales_gap(n=10, question=user_message)
                fabric_result = {"requires_approval": False, "output": format_purchase_sales_gap(result), "job_id": "sales_query"}
            elif "profitable" in lower_msg or "profit" in lower_msg:
                result = await get_most_profitable_skus(n=10, question=user_message)
                fabric_result = {"requires_approval": False, "output": format_most_profitable_skus(result), "job_id": "sales_query"}
            elif "overstock" in lower_msg:
                result = await get_overstocked_products(n=10, question=user_message)
                fabric_result = {"requires_approval": False, "output": format_overstocked_products(result), "job_id": "sales_query"}
            elif "full price" in lower_msg or "full-price" in lower_msg:
                rows = await get_full_price_sales_by_store(n=10, question=user_message)
                fabric_result = {"requires_approval": False, "output": format_full_price_sales_by_store(rows), "job_id": "sales_query"}
            elif "contribution" in lower_msg:
                rows = await get_sku_contribution(n=10, question=user_message)
                fabric_result = {"requires_approval": False, "output": format_sku_contribution(rows), "job_id": "sales_query"}
            elif "aging" in lower_msg:
                result = await get_inventory_aging(n=10, question=user_message)
                fabric_result = {"requires_approval": False, "output": format_inventory_aging(result), "job_id": "sales_query"}
            elif "return rate" in lower_msg or ("return" in lower_msg and ("rate" in lower_msg or "percentage" in lower_msg)):
                group_by = "Site" if "store" in lower_msg else "SKU"
                result = await get_return_rate(n=10, group_by=group_by, question=user_message)
                fabric_result = {"requires_approval": False, "output": format_return_rate(result), "job_id": "sales_query"}
            elif "top sku" in lower_msg:
                # Real sales data se seedha answer nikaalo — notebook/agent skip
                rows = await get_top_skus(n=10, by="qty", question=user_message)
                fabric_result = {
                    "requires_approval": False,
                    "output": format_top_skus(rows),
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
                # Run the notebook, then fetch the real output from the Lakehouse
                fabric_result = await trigger_fabric_agent(user_message)

            # If this needs approval (change/update/delete request)
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
                f"❌ Something went wrong processing that request.\n\nError: `{str(e)}`"
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

    async def _finalize_card(self, turn_context: TurnContext, result_text: str):
        """Replace the original card (the one whose button was just clicked)
        with a plain-text result, so its Approve/Reject buttons can't be
        clicked again. Best-effort — if the channel/activity doesn't support
        editing, this silently no-ops; the real correctness guard is the
        status='PENDING' check in update_recommendation_status, not this."""
        reply_to_id = turn_context.activity.reply_to_id
        if not reply_to_id:
            return
        try:
            await turn_context.update_activity(
                Activity(type=ActivityTypes.message, id=reply_to_id, text=result_text)
            )
        except Exception as e:
            print(f"[CARD FINALIZE ERROR] {e}")

    async def _handle_card_action(self, turn_context: TurnContext, value: dict):
        action = value.get("action")

        if not action:
            await turn_context.send_activity("⚠️ No valid action found on this card.")
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
                result_text = (
                    f"✅ **Transfer approved and logged.**\n\n"
                    f"**{qty} units of {sku}** — {from_store} → {to_store}\n"
                    f"Transfer ID: `{row['transfer_id']}`"
                )
            elif action == "reject":
                result_text = (
                    f"👍 Understood — this transfer request has been rejected.\n\n"
                    f"**{qty} units of {sku}** — {from_store} → {to_store}\n"
                    f"No changes were made to your stock."
                )
            else:
                await turn_context.send_activity("⚠️ Unrecognized action on this card.")
                return

            await turn_context.send_activity(result_text)
            await self._finalize_card(turn_context, result_text)
            return

        # Recommendation Approve/Reject — from Tables/dbo/final_transfer_sizewise
        if value.get("type") == "transfer_recommendation":
            if action not in ("approve", "reject"):
                await turn_context.send_activity("⚠️ Unrecognized action on this card.")
                return

            sku = value.get("sku")
            size = value.get("size")
            receiver = value.get("receiver_site_name")
            receiver_id = value.get("receiver_site_id")
            donor = value.get("donor_site_name")
            donor_id = value.get("donor_site_id")
            qty = value.get("transfer_qty")
            created_at = value.get("created_at")

            # Claim the recommendation FIRST (status='PENDING' guard) — only
            # write the stock_transfers audit row if this click actually won
            # the claim, so a second click (approve-then-reject or a replay)
            # can't create a duplicate/contradictory audit entry.
            status_result = await update_recommendation_status(
                receiver_site_id=receiver_id, donor_site_id=donor_id,
                sku=sku, size=size, created_at=created_at, transfer_qty=qty,
                status="APPROVED" if action == "approve" else "REJECTED",
            )

            if status_result["already_decided"]:
                result_text = (
                    f"⚠️ **This recommendation was already decided** — no action taken.\n\n"
                    f"**{sku} ({size})** — {donor} → {receiver}"
                )
            elif action == "approve":
                requester = turn_context.activity.from_property.name or "teams_user"
                row = await record_stock_transfer(sku, donor, receiver, qty, decided_by=requester)
                result_text = (
                    f"✅ **Recommendation approved and logged.**\n\n"
                    f"**{int(qty)} units of {sku} ({size})** — {donor} → {receiver}\n"
                    f"Transfer ID: `{row['transfer_id']}`"
                )
            else:
                result_text = (
                    f"👍 Understood — this recommendation has been rejected.\n\n"
                    f"**{sku} ({size})** — {donor} → {receiver}\n"
                    f"No changes were made to your stock."
                )

            await turn_context.send_activity(result_text)
            await self._finalize_card(turn_context, result_text)
            return

        job_id = value.get("job_id")
        summary = value.get("summary", "")

        if not job_id:
            await turn_context.send_activity("⚠️ No valid action found on this card.")
            return

        if action == "approve":
            result = await execute_fabric_action(job_id, approved=True)
            result_text = (
                f"✅ **Approved.**\n\n"
                f"**Action:** {summary}\n"
                f"**Status:** Pipeline is running...\n"
                f"**Job ID:** `{job_id}`"
            )

        elif action == "reject":
            await execute_fabric_action(job_id, approved=False)
            result_text = (
                f"👍 Understood — this request has been rejected.\n\n"
                f"**Action:** {summary}\n"
                f"No changes were made."
            )

        else:
            await turn_context.send_activity("⚠️ Unrecognized action on this card.")
            return

        await turn_context.send_activity(result_text)
        await self._finalize_card(turn_context, result_text)
