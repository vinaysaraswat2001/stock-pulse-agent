# Stockpulse Teams Bot — FastAPI + Microsoft Fabric Agent

## Architecture
```
Teams User → Azure Bot Service → FastAPI Bot → Microsoft Fabric Agent
```

---

## Project Structure
```
stockpulse-teambot/
├── main.py            # FastAPI entry point
├── bot.py             # Bot logic (message + approve/reject)
├── fabric_client.py   # Fabric REST API calls
├── adaptive_card.py   # Approve/Reject + Result cards
├── requirements.txt
├── startup.sh         # Azure App Service startup
└── .env.example       # Environment variables template
```

---

## Step 1 — Local Setup

```bash
# Clone/copy karo
cd stockpulse-teambot

# Virtual env
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# .env file banao
cp .env.example .env
# .env me apni values fill karo
```

---

## Step 2 — .env Fill Karo

```env
BOT_APP_ID=           ← Azure Bot Service → Configuration → Microsoft App ID
BOT_APP_SECRET=       ← App Registration → Certificates & Secrets → New Secret
TENANT_ID=            ← Azure Active Directory → Overview → Tenant ID
FABRIC_CLIENT_ID=     ← App Registration (Fabric access wala) → Client ID
FABRIC_CLIENT_SECRET= ← App Registration → Certificates & Secrets
FABRIC_WORKSPACE_ID=  ← Fabric Portal → Workspace → URL se copy karo
FABRIC_AGENT_ITEM_ID= ← Fabric Portal → Agent item → URL se copy karo
FABRIC_LAKEHOUSE_ID=  ← Fabric Portal → Lakehouse item → URL se copy karo (notebook output write-back ke liye)
```

---

## Step 3 — Local Test

```bash
uvicorn main:app --reload --port 8000

# Ngrok se public URL lo (local testing ke liye)
ngrok http 8000

# Ngrok URL copy karo: https://xxxx.ngrok.io
```

---

## Step 4 — Azure Bot Service Messaging Endpoint Set Karo

```
Azure Portal → Stockpulse-teambot → Configuration
→ Messaging Endpoint: https://YOUR-APP-URL/api/messages
→ Apply
```

---

## Step 5 — Azure App Service Deploy

```bash
# Azure CLI se deploy
az webapp up \
  --name stockpulse-teambot \
  --resource-group AI-Team \
  --runtime "PYTHON:3.11"

# Environment variables set karo
az webapp config appsettings set \
  --name stockpulse-teambot \
  --resource-group AI-Team \
  --settings \
    BOT_APP_ID="xxx" \
    BOT_APP_SECRET="xxx" \
    TENANT_ID="xxx" \
    FABRIC_CLIENT_ID="xxx" \
    FABRIC_CLIENT_SECRET="xxx" \
    FABRIC_WORKSPACE_ID="xxx" \
    FABRIC_AGENT_ITEM_ID="xxx"
```

---

## Step 6 — Teams me Test Karo

```
Azure Bot Service → Channels → Microsoft Teams → Open in Teams
```

---

## Fabric Agent REST API — Key Endpoints

| Action | Endpoint |
|--------|----------|
| Job Trigger | POST /workspaces/{id}/items/{agentId}/jobs/instances |
| Job Status  | GET  /workspaces/{id}/items/{agentId}/jobs/instances/{jobId} |
| Job Action  | POST /workspaces/{id}/items/{agentId}/jobs/instances/{jobId}/action |

---

## Approve/Reject Flow

```
User: "Delete last week's data"
        ↓
Fabric Agent returns requires_approval: true
        ↓
Bot shows Adaptive Card with ✅ Approve / ❌ Reject buttons
        ↓
User clicks → Bot calls execute_fabric_action(approved=True/False)
        ↓
Fabric executes or cancels the action
```
