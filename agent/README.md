# StockPulse Agent

Conversation-first Microsoft Teams Agent for inventory and stock transfer alerts.

## Architecture

```
Teams Chat
    ↓
Bot (bot.py)
    ↓
Agent Router (agent/router.py)
    ↓
Data Service (mock → Fabric in Phase 5)
    ↓
Card Factory (Adaptive Cards 1.5 + Action.Execute)
    ↓
Teams Chat (next card)
```

## Folder structure

```
stockpulse-agentbackend/
├── agent/
│   ├── cards/              # Adaptive Card JSON templates (reference)
│   │   ├── welcome-card.json
│   │   ├── summary-card.json
│   │   ├── critical-card.json
│   │   ├── store-card.json
│   │   ├── transfer-card.json
│   │   ├── approval-card.json
│   │   └── success-card.json
│   ├── mock_data/
│   │   └── alerts.json     # Phase 1–3 mock data
│   ├── bot_handler.py      # Teams invoke + card attachment helpers
│   ├── card_factory.py     # Runtime card builders (Action.Execute)
│   ├── data_service.py     # Mock data access (swap for Fabric later)
│   ├── models.py           # API contracts (Pydantic)
│   ├── router.py           # Verb → next card
│   └── routes.py           # FastAPI /api/v1/agent/*
├── bot.py                  # Bot Framework entry (delegates to agent)
├── main.py                 # FastAPI + /api/messages
├── alerts.py               # Legacy dashboard API (admin portal — keep)
└── docs/
    ├── CONVERSATION_FLOW.md
    └── API_CONTRACTS.md
```

## Conversation flow

See [docs/CONVERSATION_FLOW.md](docs/CONVERSATION_FLOW.md)

## Quick test (no Teams)

```bash
# Welcome card
curl http://localhost:8000/api/v1/agent/welcome?userName=Harsh

# Summary card
curl http://localhost:8000/api/v1/agent/alerts/summary

# Simulate button click
curl -X POST http://localhost:8000/api/v1/agent/action \
  -H "Content-Type: application/json" \
  -d '{"verb":"show_critical","data":{},"user_name":"Harsh"}'
```

## Phases

| Phase | Scope |
|-------|--------|
| 1 | Agent setup, card framework, mock data ✅ |
| 2 | Welcome, Summary, Critical cards ✅ |
| 3 | Approve/Reject, Action.Execute ✅ |
| 4 | FastAPI + Fabric integration |
| 5 | Lakehouse live data |
| Future | GPT intent, WebSockets, M365 Agents SDK |

## React dashboard

`StockPulse_Agentfrontend` is **kept** as UX reference and future Admin/Ops portal.
It is **not** the primary Teams user experience.
