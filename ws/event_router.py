# ws/event_router.py
from fastapi import APIRouter, WebSocket
import asyncio
from .event_manager import event_manager  # your updated event manager

router = APIRouter()

@router.websocket("/ws/market")
async def events_ws(ws: WebSocket):
    await event_manager.connect(ws)

    try:
        while True:
            # Optionally wait for subscription message
            # If the frontend sends {"symbol": "GBPJPY"} to /ws/market
            data = await ws.receive_text()
            init_data = json.loads(data)
            symbol = init_data.get("symbol")
            tf = init_data.get("tf") or init_data.get("timeframe")
            if symbol:
                event_manager.subscribe(ws, symbol, tf)
                print(f"🔄 Event subscription: {symbol} ({tf})")

    except Exception as e:
        print(f"🔴 Event WS disconnected: {e}")
    finally:
        event_manager.disconnect(ws)

