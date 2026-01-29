# ws/router.py
from fastapi import APIRouter, WebSocket
from .manager import ws_manager
import json
import asyncio
from asyncio import CancelledError


router = APIRouter()

@router.websocket("/ws/candles/{pair}")
async def ws_stream(ws: WebSocket, pair: str):
    pair = pair.upper()
    # Explicitly reject candle WS connections — candles are served from CSV on frontend.
    await ws.accept()
    try:
        await ws.send_text(json.dumps({"type": "error", "message": "Candle WS disabled. Load candles from CSV."}))
    except Exception:
        pass
    await ws.close()
    print(f"🛑 Rejected candle WS connection for {pair}")
    return