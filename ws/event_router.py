# ws/event_router.py
from fastapi import APIRouter, WebSocket
import asyncio
from .event_manager import event_manager  # your updated event manager

router = APIRouter()

@router.websocket("/ws/market/{pair}")
async def events_ws(ws: WebSocket, pair: str):
    pair = pair.upper()
    await ws.accept()
    await event_manager.connect(ws, pair)
    num_clients = len(event_manager.clients.get(pair, []))
    print(f"🟢 client-{num_clients} connected to marketws for {pair}")

    try:
        while True:
            await ws.receive_text()
            # Optionally wait for subscription message
            # If the frontend sends {"symbol": "GBPJPY"} to /ws/market
            # data = await ws.receive_text()
            # init_data = json.loads(data)
            # symbol = init_data.get("symbol")
            # tf = init_data.get("tf") or init_data.get("timeframe")
            # if symbol:
            #     event_manager.subscribe(ws, symbol, tf)
            #     print(f"🔄 Event subscription: {symbol} ({tf})")

    except Exception as e:
        print(f"🔴 Event WS disconnected: {e}")
    finally:
        event_manager.disconnect(ws, pair)

