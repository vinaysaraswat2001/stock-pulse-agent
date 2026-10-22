# StockPulse Agent — API Contracts

Base URL: `/api/v1/agent`

## POST /action

Simulates Teams `Action.Execute` for testing without Bot channel.

### Request

```json
{
  "verb": "show_critical",
  "data": { "storeId": "store-gurgaon" },
  "user_id": "29:optional-teams-id",
  "user_name": "Harsh Bhardwaj"
}
```

### Response

```json
{
  "card_type": "critical_list",
  "card": { "$schema": "...", "type": "AdaptiveCard", "version": "1.5", "body": [], "actions": [] },
  "message": null
}
```

## GET /welcome?userName=Harsh

Returns welcome card bound with user name.

## GET /alerts/summary

Returns today's alerts summary card (mock data).

## GET /cards/{card_type}/preview

Returns attachment wrapper for Bot Framework testing.

Supported `card_type`: `welcome`, `summary`, `critical`

---

## Action.Execute payload (Teams → Bot)

Teams sends invoke `adaptiveCard/action`:

```json
{
  "action": {
    "type": "Action.Execute",
    "verb": "review_store",
    "data": { "storeId": "store-gurgaon" }
  }
}
```

Bot responds with InvokeResponse:

```json
{
  "statusCode": 200,
  "type": "application/vnd.microsoft.card.adaptive",
  "value": { "...next Adaptive Card..." }
}
```

---

## Data DTOs (mock → Fabric)

### AlertSummary

| Field | Type |
|-------|------|
| date | string |
| critical | int |
| medium | int |
| low | int |
| total | int |

### StoreSummary

| Field | Type |
|-------|------|
| id | string |
| name | string |
| city | string |
| critical, medium, low | int |
| alertCount | int |

### Transfer

| Field | Type |
|-------|------|
| id | string |
| sku | string |
| size | string |
| requiredQty | int |
| transferQty | int |
| receiverSoh | int |
| donorSoh | int |
| donorStore | string |
| scope | string |
| status | PENDING \| APPROVED \| REJECTED |

---

## Phase 4 swap

Replace `agent/data_service.py` implementation with Fabric calls.
Keep `router.py`, `card_factory.py`, and API contracts unchanged.
