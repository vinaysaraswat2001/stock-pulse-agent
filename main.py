import os
import asyncio
from fastapi import FastAPI, Request, Response
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
from botbuilder.schema import Activity
from bot import StockpulseBot
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Stockpulse Teams Bot")

BOT_APP_ID     = "b1c33470-25d0-436f-9d7b-689aaea51b59"
BOT_APP_SECRET = os.getenv("BOT_APP_SECRET", "")
TENANT_ID      = "a8801bcb-7990-408e-ab0c-e73eccd70288"

# Debug — startup pe print karo (secret ka sirf first 4 chars)
print(f"[STARTUP] BOT_APP_ID     = {BOT_APP_ID}")
print(f"[STARTUP] BOT_APP_SECRET = {BOT_APP_SECRET[:4]}**** (len={len(BOT_APP_SECRET)})")
print(f"[STARTUP] TENANT_ID      = {TENANT_ID}")

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

    await adapter.process_activity(activity, auth_header, call_bot)
    return Response(status_code=200)