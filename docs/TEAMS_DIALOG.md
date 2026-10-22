# Teams Agent — Adaptive Cards + Dialog

Conversation-first StockPulse prototype. No dashboard in the primary Teams flow.

## Flow

```
User chats with bot
    → Compact Adaptive Card (alert summary)
    → [View Alerts] button
    → Teams Task Module (dialog popup)
    → React UI at /#/dialog (mock data)
```

## Architecture

| Layer | Path | Role |
|-------|------|------|
| Compact card | `agent/task_module.py` | Summary KPIs + `task/fetch` button |
| Bot invoke | `bot.py` → `task/fetch`, `task/submit` | Opens / closes dialog |
| Dialog UI | `StockPulse_Agentfrontend/src/pages/Dialog/` | Popup-optimized React |
| Mock data | `src/data/mockAlerts.js` | `VITE_USE_MOCK=true` (default) |
| Dashboard | `/#/stock-alerts` | Reference only — not primary UX |

## Dialog UI includes

- Search (compact)
- Accordion: Zone → City → Store Type → Store
- Store transfer list
- Transfer detail + Approve / Reject / Escalate
- No KPI cards, no top nav, no bulk bar

## Local dev

### 1. Frontend (dialog host)

```bash
cd StockPulse_Agentfrontend
npm run dev
# Preview dialog: http://localhost:5173/?view=dialog
```

### 2. Backend (bot)

```bash
cd stockpulse-agentbackend
# Set public URL of frontend (dev tunnel / ngrok) — NO hash path
# DIALOG_BASE_URL=https://your-tunnel.devtunnels.ms
uvicorn main:app --reload --port 8001
```

Bot opens: `{DIALOG_BASE_URL}/?view=dialog`  
(Do **not** use `#/dialog` — Teams iframes often strip the hash and show a blank white popup.)

### 3. Teams

1. Expose frontend via dev tunnel (port 5173)
2. Set `DIALOG_BASE_URL` in backend `.env` to tunnel URL
3. Add tunnel host to `teams-app/manifest.json` → `validDomains`
4. Upload manifest to Teams
5. Chat **hi** → compact card → **View Alerts**

## Env vars

| Variable | Where | Purpose |
|----------|-------|---------|
| `DIALOG_BASE_URL` | backend `.env` | Public URL for `/#/dialog` |
| `VITE_USE_MOCK` | frontend `.env` | `true` = mock alerts (default) |

## Modular next steps

- Wire dialog to FastAPI `/api/v1/alerts` when ready
- Push critical alerts as compact notification card + View Alert → dialog deep link
- Move more actions back into Adaptive Cards if needed (hybrid model)
