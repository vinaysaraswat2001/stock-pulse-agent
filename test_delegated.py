import httpx, json
from msal import PublicClientApplication

# ─── Zink Tenant (Fabric wala) ──────────────────
ZINK_TENANT_ID = "aca0b239-69e9-4246-87ba-8e07ad0a9249"

# Microsoft Azure CLI — public app (no registration needed)
MS_CLI_CLIENT_ID = "04b07795-8542-4c97-a140-f9e94a983a88"

# ─── Fabric Endpoint ─────────────────────────────
BASE_URL     = "https://c41f5d1b6702478cae1ce64b8e8dc358.pbidedicated.windows.net"
CAPACITY_ID  = "C41F5D1B-6702-478C-AE1C-E64B8E8DC358"
WORKSPACE_ID = "411f437b-71b5-4416-b399-86a34e5518dc"
ARTIFACT_ID  = "c8ba6773-005d-42dc-85c6-7cae2a9dc726"
API_VERSION  = "2024-05-01-preview"

AI_BASE = (
    f"{BASE_URL}/webapi/capacities/{CAPACITY_ID}"
    f"/workloads/ML/AISkill/Automatic/v1"
    f"/workspaces/{WORKSPACE_ID}/artifacts/{ARTIFACT_ID}"
    f"/aiassistant/openai"
)

# ─── Token — Zink tenant se ──────────────────────
app = PublicClientApplication(
    client_id=MS_CLI_CLIENT_ID,
    authority=f"https://login.microsoftonline.com/{ZINK_TENANT_ID}"
)

result = app.acquire_token_by_username_password(
    username="admin@zinklondon1.onmicrosoft.com",
    password="Meridian#123",   # ← Naya password daalo
    scopes=["https://analysis.windows.net/powerbi/api/.default"]
)

if "access_token" not in result:
    print(f"❌ Token failed: {result.get('error_description')}")
    exit()

print("✅ Token OK!")
token = result["access_token"]

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

with httpx.Client(timeout=60) as client:

    # Step 1 — Thread banao
    print("\n[1] Creating thread...")
    r1 = client.post(
        f"{AI_BASE}/threads?api-version={API_VERSION}",
        headers=headers,
        json={}
    )
    print(f"Status: {r1.status_code}")
    print(f"Response: {r1.text[:300]}")

    if r1.status_code != 200:
        print("❌ Thread creation failed!")
        exit()

    thread_id = r1.json().get("id")
    print(f"✅ Thread ID: {thread_id}")

    # Step 2 — Message add karo
    print("\n[2] Adding message...")
    r2 = client.post(
        f"{AI_BASE}/threads/{thread_id}/messages?api-version={API_VERSION}",
        headers=headers,
        json={"role": "user", "content": "give me top skus"}
    )
    print(f"Status: {r2.status_code}")
    print(f"Response: {r2.text[:200]}")

    # Step 3 — Run karo
    print("\n[3] Running agent...")
    r3 = client.post(
        f"{AI_BASE}/threads/{thread_id}/runs?api-version={API_VERSION}",
        headers=headers,
        json={"assistant_id": ARTIFACT_ID}
    )
    print(f"Status: {r3.status_code}")
    print(f"Response: {r3.text[:500]}")

    # Step 4 — Messages fetch karo (result)
    if r3.status_code == 200:
        import time
        print("\n[4] Waiting for response...")
        time.sleep(10)

        r4 = client.get(
            f"{AI_BASE}/threads/{thread_id}/messages?api-version={API_VERSION}&limit=100",
            headers=headers
        )
        print(f"Status: {r4.status_code}")
        print(f"Response: {json.dumps(r4.json(), indent=2)[:1000]}")