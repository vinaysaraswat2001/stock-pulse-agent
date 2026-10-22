# StockPulse Agent — Conversation Flow

## Principle

**Conversation = navigation.** Every button uses `Action.Execute`. The backend returns the next Adaptive Card. No web pages, no tabs, no drawers.

## Flow diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER OPENS TEAMS CHAT                        │
└───────────────────────────────┬─────────────────────────────────┘
                                ▼
                    ┌───────────────────────┐
                    │    WELCOME CARD        │
                    │  StockPulse AI         │
                    │  Hello {name}          │
                    │  [Stock Alerts]        │
                    │  [Critical Alerts]     │
                    │  [Inventory Summary]   │
                    │  [Dead Stock]          │
                    │  [Top Selling SKUs]    │
                    └───────────┬───────────┘
                                │ Action.Execute: show_alerts_summary
                                ▼
                    ┌───────────────────────┐
                    │   SUMMARY CARD         │
                    │  Critical: 12          │
                    │  Medium: 31            │
                    │  Low: 48               │
                    │  [View Critical]       │
                    │  [View Medium/Low]     │
                    │  [View By Store]       │
                    │  [Refresh] [Home]      │
                    └───────────┬───────────┘
                                │ Action.Execute: show_critical
                                ▼
                    ┌───────────────────────┐
                    │  CRITICAL LIST CARD    │
                    │  Store Gurgaon — 7     │
                    │  Store Delhi — 5       │
                    │  Store Jaipur — 2      │
                    │  [Review] per store    │
                    └───────────┬───────────┘
                                │ Action.Execute: review_store
                                ▼
                    ┌───────────────────────┐
                    │   STORE DETAIL CARD    │
                    │  Name, counts, grades  │
                    │  [Open Transfers]      │
                    │  [Back] [Home]         │
                    └───────────┬───────────┘
                                │ Action.Execute: open_transfers
                                ▼
                    ┌───────────────────────┐
                    │   TRANSFER CARD        │
                    │  SKU, Size, Qty, SOH   │
                    │  [Approve] [Reject]    │
                    │  [Next] [Previous]     │
                    │  [Back to Store]       │
                    └───────────┬───────────┘
                                │ Action.Execute: approve_transfer
                                ▼
                    ┌───────────────────────┐
                    │   SUCCESS CARD         │
                    │  Transfer Approved     │
                    │  Approved by, time     │
                    │  [Next Transfer]       │
                    │  [Back to Alerts]      │
                    └───────────────────────┘
```

## Verb catalog

| Verb | From card | Returns |
|------|-----------|---------|
| `show_welcome` | Any | Welcome |
| `show_alerts_summary` | Welcome, Success | Summary |
| `show_critical` | Welcome, Summary | Critical store list |
| `show_medium` | Summary | Medium store list |
| `show_low` | Summary | Low store list |
| `show_by_store` | Summary | All stores list |
| `refresh_summary` | Summary | Summary (reload) |
| `review_store` | Store list | Store detail |
| `open_transfers` | Store detail | Transfer (index 0) |
| `next_transfer` | Transfer, Success | Transfer (index+1) |
| `previous_transfer` | Transfer | Transfer (index-1) |
| `approve_transfer` | Transfer | Success |
| `reject_transfer` | Transfer | Success (rejected) |

## UX rules

1. **Aggregate** — one summary card, not one card per alert
2. **Max ~6 actions** per card (Microsoft guidance: 1–3 primary)
3. **No Action.OpenUrl** for operational flows
4. **Action.Execute only** on agent cards
5. **Invoke response** replaces card in-place when Teams supports it
6. **No chat flooding** — sequential workflow, not broadcast

## Natural language entry (Phase 1)

| User says | Agent returns |
|-----------|---------------|
| hi / hello / help | Welcome card |
| stock alerts | Summary card |
| critical alerts | Critical list card |

Future: GPT intent classification maps free text → same verbs.
