import os
import json
import uuid
import asyncio
import httpx
from openai import AsyncOpenAI
from msal import ConfidentialClientApplication
from dotenv import load_dotenv

from query_log import log_fetch

load_dotenv(override=True)

BOT_TENANT_ID        = os.getenv("TENANT_ID")

# ─── Fabric Credentials (from .env; hardcoded fallback for local dev only) ─
FABRIC_TENANT_ID     = os.getenv("FABRIC_TENANT_ID")
FABRIC_CLIENT_ID     = os.getenv("FABRIC_CLIENT_ID")
FABRIC_CLIENT_SECRET = os.getenv("FABRIC_CLIENT_SECRET")
WORKSPACE_ID  = os.getenv("FABRIC_WORKSPACE_ID")
AGENT_ITEM_ID = os.getenv("FABRIC_AGENT_ITEM_ID")

# GUID of the Lakehouse the notebook writes its results into (Fabric portal →
# open the Lakehouse → copy the GUID from the URL after /lakehouses/).
LAKEHOUSE_ID = os.getenv("FABRIC_LAKEHOUSE_ID", "")

FABRIC_BASE_URL  = "https://api.fabric.microsoft.com/v1"
FABRIC_SCOPE     = ["https://api.fabric.microsoft.com/.default"]
ONELAKE_SCOPE    = ["https://storage.azure.com/.default"]
ONELAKE_DFS_HOST = "https://onelake.dfs.fabric.microsoft.com"

print(f"[FABRIC] TENANT_ID = {FABRIC_TENANT_ID}")
print(f"[FABRIC] CLIENT_ID = {FABRIC_CLIENT_ID}")# ─── Bot Tenant (Azure Bot Service wala) ────────



# ─── Get Access Token ────────────────────────────

def get_fabric_token() -> str:
    msal_app = ConfidentialClientApplication(
        client_id=FABRIC_CLIENT_ID,
        client_credential=FABRIC_CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{FABRIC_TENANT_ID}"  # ← Fabric tenant
    )
    token_response = msal_app.acquire_token_for_client(scopes=FABRIC_SCOPE)
# One shared MSAL app instance so its internal token cache actually works —
# creating a fresh ConfidentialClientApplication per call (the old code) means
# every single token request re-authenticates over the network from scratch,
# even seconds apart. Reusing the instance lets MSAL serve cached, unexpired
# tokens instantly instead.
_msal_app: ConfidentialClientApplication | None = None


def _get_msal_app() -> ConfidentialClientApplication:
    global _msal_app
    if _msal_app is None:
        _msal_app = ConfidentialClientApplication(
            client_id=FABRIC_CLIENT_ID,
            client_credential=FABRIC_CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{FABRIC_TENANT_ID}"
        )
    return _msal_app


def get_fabric_token() -> str:
    token_response = _get_msal_app().acquire_token_for_client(scopes=FABRIC_SCOPE)


    if "access_token" not in token_response:
        raise Exception(f"Token error: {token_response.get('error_description')}")

    return token_response["access_token"]


def get_onelake_token() -> str:

    msal_app = ConfidentialClientApplication(
        client_id=FABRIC_CLIENT_ID,
        client_credential=FABRIC_CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{FABRIC_TENANT_ID}"
    )
 
    token_response = _get_msal_app().acquire_token_for_client(scopes=ONELAKE_SCOPE)


    if "access_token" not in token_response:
        raise Exception(f"Token error: {token_response.get('error_description')}")

    return token_response["access_token"]


# ─── Fetch the notebook's written-back result from the Lakehouse ─
# Notebook must write its answer to Files/results/{run_id}.json using
# notebookutils.fs.put() (see README for the exact notebook-side snippet).
async def fetch_notebook_result(run_id: str) -> str | None:
    if not LAKEHOUSE_ID:
        print("[ONELAKE] FABRIC_LAKEHOUSE_ID not configured — skipping result fetch")
        return None

    token = get_onelake_token()
    url = f"{ONELAKE_DFS_HOST}/{WORKSPACE_ID}/{LAKEHOUSE_ID}/Files/results/{run_id}.json"

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "x-ms-version": "2023-11-03",
            }
        )
        if r.status_code == 404:
            print(f"[ONELAKE] No result file yet at {url}")
            return None
        r.raise_for_status()

        try:
            data = r.json()
            return data.get("answer") or data.get("output") or json.dumps(data)
        except ValueError:
            return r.text


# ─── Query the Fabric Data Agent (real Q&A, not a notebook run) ──
# Fabric Data Agents expose an OpenAI Assistants-API-compatible endpoint.
# Docs: https://learn.microsoft.com/en-us/fabric/data-science/consume-data-agent-python
DATA_AGENT_URL = f"{FABRIC_BASE_URL}/workspaces/{WORKSPACE_ID}/aiskills/{AGENT_ITEM_ID}/aiassistant/openai"


async def query_data_agent(user_input: str, max_wait_seconds: int = 90) -> dict:
    log_fetch("data_agent", f"Fabric Data Agent {AGENT_ITEM_ID} (workspace {WORKSPACE_ID})", user_input)
    token = get_fabric_token()
    client = AsyncOpenAI(
        api_key=token,
        base_url=DATA_AGENT_URL,
        default_query={"api-version": "2024-05-01-preview"},
    )

    assistant = await client.beta.assistants.create(model="not used")
    thread = await client.beta.threads.create()
    await client.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=user_input
    )
    run = await client.beta.threads.runs.create(
        thread_id=thread.id, assistant_id=assistant.id
    )

    poll_interval = 2
    waited = 0
    while run.status in ("queued", "in_progress"):
        if waited >= max_wait_seconds:
            raise Exception("Data agent timed out waiting for a response")
        await asyncio.sleep(poll_interval)
        waited += poll_interval
        run = await client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        print(f"[DATA AGENT] Run status: {run.status}")

    if run.status != "completed":
        raise Exception(f"Data agent run ended with status: {run.status}")

    messages = await client.beta.threads.messages.list(thread_id=thread.id, order="asc")
    assistant_messages = [m for m in messages.data if m.role == "assistant"]

    if not assistant_messages:

        answer = "No response was received from the data agent."

    else:
        last = assistant_messages[-1]
        answer = "\n".join(
            block.text.value for block in last.content if block.type == "text"
        )

    return {
        "requires_approval": False,
        "output": answer,
        "job_id": thread.id
    }


# ─── Trigger Fabric Agent (notebook batch job — no data returned) ─
async def trigger_fabric_agent(user_input: str) -> dict:
    token = get_fabric_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    NOTEBOOK_ID = "9546e51e-008c-462c-adc8-73a323aee050"
    run_id = str(uuid.uuid4())
    log_fetch("notebook_trigger", f"Fabric Notebook {NOTEBOOK_ID} 'date_groupby_sales' (workspace {WORKSPACE_ID}, run_id={run_id})", user_input)

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/items/{NOTEBOOK_ID}/jobs/instances?jobType=RunNotebook",
            headers=headers,
            json={
                "executionData": {
                    "parameters": {
                        "user_query": {"value": user_input, "type": "string"},
                        "run_id": {"value": run_id, "type": "string"}
                    }
                }
            }
        )
        print(f"[FABRIC] Status: {response.status_code}")
        print(f"[FABRIC] Headers: {dict(response.headers)}")

        # 202 = Job triggered — Location header me job URL hogi
        if response.status_code == 202:
            location = response.headers.get("Location") or response.headers.get("location")
            print(f"[FABRIC] Location: {location}")

            if location:
                # Job complete hone ka wait karo
                result = await poll_notebook_job(location, token, run_id)
                return result
            else:
                # Job triggered but no location — success maano
                return {
                    "requires_approval": False,

                    "output": "✅ Pipeline triggered successfully. The result will be ready shortly.",

                    "job_id": "notebook"
                }

        response.raise_for_status()
        return {
            "requires_approval": False,
            "output": str(response.json()),
            "job_id": "notebook"
        }


async def poll_notebook_job(location: str, token: str, run_id: str, max_attempts: int = 40) -> dict:
    headers = {"Authorization": f"Bearer {token}"}

    for attempt in range(max_attempts):
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(location, headers=headers)
            data = r.json()
            status = data.get("status", "").lower()
            print(f"[FABRIC POLL] Attempt {attempt+1} Status: {status}")
            print(f"[FABRIC POLL] Full Response: {json.dumps(data, indent=2)}")

            if status in ["succeeded", "completed", "success"]:
                job_id = data.get("id")

                # Job status API doesn't carry notebook results — the notebook
                # writes its answer to Files/results/{run_id}.json instead.
                try:
                    output = await fetch_notebook_result(run_id)
                    if not output:
                        output = "✅ Job completed. The output has been saved to the notebook."
                except Exception as e:
                    print(f"[ONELAKE FETCH ERROR] {e}")
                    output = "✅ Job completed successfully!"

                return {
                    "requires_approval": False,
                    "output": str(output),
                    "job_id": job_id
                }

            elif status in ["failed", "error", "cancelled"]:
                reason = data.get("failureReason") or "Unknown"
                raise Exception(f"Job failed: {reason}")

        wait = 3 if attempt < 10 else 5
        await asyncio.sleep(wait)

    return {
        "requires_approval": False,
        "output": "⏳ The job is still running in the background.",
        "job_id": "notebook"
    }

# ─── Approve / Reject Action ─────────────────────
async def execute_fabric_action(job_id: str, approved: bool) -> dict:
    token = get_fabric_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{FABRIC_BASE_URL}/workspaces/{WORKSPACE_ID}/items/{AGENT_ITEM_ID}/jobs/instances/{job_id}/action",
            headers=headers,
            json={"approved": approved}
        )
        response.raise_for_status()

    return response.json() if response.content else {"status": "ok"}