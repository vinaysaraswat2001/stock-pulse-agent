import os
import traceback
from fastapi import FastAPI, Request, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity
from bot import StockpulseBot
from lakehouse_client import get_stock_transfers
from agent.routes import agent_api
from alerts import (
    StatusUpdateBody,
    list_alerts_response,
    list_store_alerts_response,
    get_alert_by_id,
    update_alerts_status,
    build_filter_options,
)
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="StockPulse Agent API")
app.include_router(agent_api)

# Allow the Vite dashboard (and Teams tabs) to call /api/v1/*
_cors_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins if "*" not in _cors_origins else ["*"],
    allow_credentials="*" not in _cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return JSON errors with CORS-friendly headers instead of plain-text 500s."""
    print(f"[UNHANDLED] {request.method} {request.url.path}: {type(exc).__name__}: {exc}")
    traceback.print_exc()
    origin = request.headers.get("origin")
    headers = {}
    if origin and (origin in _cors_origins or "*" in _cors_origins):
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) or "Internal Server Error"},
        headers=headers,
    )

BOT_APP_ID     = "b1c33470-25d0-436f-9d7b-689aaea51b59"
BOT_APP_SECRET = os.getenv("BOT_APP_SECRET", "")
TENANT_ID      = "a8801bcb-7990-408e-ab0c-e73eccd70288"

# Debug — startup pe print karo (secret ka sirf first 4 chars)
print(f"[STARTUP] BOT_APP_ID     = {BOT_APP_ID}")
print(f"[STARTUP] BOT_APP_SECRET = {BOT_APP_SECRET[:4]}**** (len={len(BOT_APP_SECRET)})")
print(f"[STARTUP] TENANT_ID      = {TENANT_ID}")

_dialog_url = os.getenv("DIALOG_BASE_URL", "http://localhost:5173")
print(f"[STARTUP] DIALOG_BASE_URL = {_dialog_url}")
if "localhost" in _dialog_url or "127.0.0.1" in _dialog_url:
    print(
        "[STARTUP] WARNING: DIALOG_BASE_URL is localhost — Teams cannot open the dialog. "
        "Set DIALOG_BASE_URL to your public HTTPS dev tunnel URL (port 5173)."
    )

# Bot Adapter Setup — Single Tenant ke liye channel_auth_tenant zaroori hai
settings = BotFrameworkAdapterSettings(
    app_id=BOT_APP_ID,
    app_password=BOT_APP_SECRET,
    channel_auth_tenant=TENANT_ID   # ← Yeh fix hai Single Tenant ke liye
)
adapter = BotFrameworkAdapter(settings)
bot = StockpulseBot()


# Error Handler — sirf log karo, reply mat karo (reply bhi token maangta hai)
async def on_error(context: TurnContext, error: Exception):
    print(f"[BOT ERROR] {type(error).__name__}: {error}")

adapter.on_turn_error = on_error


@app.get("/")
async def health():
    return {"status": "✅ Stockpulse Bot is running!"}


@app.post("/api/messages")
async def messages(request: Request):
    if "application/json" not in request.headers.get("Content-Type", ""):
        return Response(status_code=415)

    body = await request.json()
    activity = Activity().deserialize(body)
    auth_header = request.headers.get("Authorization", "")

    async def call_bot(turn_context: TurnContext):
        await bot.on_turn(turn_context)

    # CRITICAL: return invoke body for task/fetch — otherwise Teams shows
    # "Unable to reach app. Please try again."
    invoke_response = await adapter.process_activity(activity, auth_header, call_bot)
    if invoke_response is not None:
        return JSONResponse(
            status_code=invoke_response.status or 200,
            content=invoke_response.body or {},
        )
    return Response(status_code=200)


@app.get("/api/transfers")
async def transfers(
    sku: str | None = Query(default=None, description="Filter to one SKU (exact match)"),
    store: str | None = Query(default=None, description="Filter to a store (substring match, either side)"),
    limit: int = Query(default=100, le=1000),
):
    """Read-only view of Tables/dbo/stock_transfers — every transfer approved
    (or attempted) via the bot's Approve/Reject cards, most recent first.

    NOTE: unauthenticated. Anyone with the ngrok URL can call this. Add an
    API key or Azure AD auth before relying on this beyond internal testing.
    """
    rows = await get_stock_transfers(sku=sku, store=store, limit=limit)
    return {"count": len(rows), "transfers": rows}


# ─── Stock Alerts dashboard API (matches StockPulse_Agentfrontend contract) ───

@app.get("/api/v1/alerts")
async def alerts_list(
    search: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    location: str | None = Query(default=None),
    product: str | None = Query(default=None),
    status: str | None = Query(default=None),
    zone: str | None = Query(default=None),
    region: str | None = Query(default=None),
    city: str | None = Query(default=None),
    store: str | None = Query(default=None),
    storeType: str | None = Query(default=None),
    storeId: str | None = Query(default=None),
    dateFrom: str | None = Query(default=None),
    dateTo: str | None = Query(default=None),
    sortBy: str = Query(default="timestamp"),
    sortDir: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=500),
):
    try:
        return await list_alerts_response(
            search=search,
            severity=severity,
            location=location,
            product=product,
            status=status,
            zone=zone,
            region=region,
            city=city,
            store=store,
            store_type=storeType,
            store_id=storeId,
            date_from=dateFrom,
            date_to=dateTo,
            sort_by=sortBy,
            sort_dir=sortDir,
            page=page,
            page_size=pageSize,
        )
    except Exception as exc:
        print(f"[ALERTS ERROR] {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/api/v1/alerts/by-store")
async def alerts_by_store(
    storeId: str | None = Query(default=None, description="Receiver site id"),
    storeName: str | None = Query(default=None, description="Receiver store name"),
    sortBy: str = Query(default="timestamp"),
    sortDir: str = Query(default="desc"),
):
    """All transfer alerts for one store from final_transfer_sizewise."""
    try:
        return await list_store_alerts_response(
            store_id=storeId,
            store_name=storeName,
            sort_by=sortBy,
            sort_dir=sortDir,
        )
    except Exception as exc:
        print(f"[STORE ALERTS ERROR] {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.get("/api/v1/alerts/filters")
async def alerts_filters():
    # Static + empty dynamic lists; list endpoint also returns live filterOptions
    return {"data": build_filter_options([])}


@app.get("/api/v1/alerts/{alert_id}")
async def alerts_detail(alert_id: str):
    return await get_alert_by_id(alert_id)


@app.patch("/api/v1/alerts/status")
async def alerts_status(body: StatusUpdateBody):
    return await update_alerts_status(body.ids, body.status)

