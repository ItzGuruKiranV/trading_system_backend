# ws/router.py
from fastapi import APIRouter, WebSocket
from .manager import ws_manager
import json

router = APIRouter()

@router.websocket("/ws/candles")
async def ws_stream(ws: WebSocket):
    await ws_manager.connect(ws)
    print("WS connected")

    try:
        # 1. Wait for init message: { symbol: "EURUSD", tf: "5m" }
        data = await ws.receive_text()
        init_data = json.loads(data)
        print(f"✅ Subscription received: {init_data}")
        
        while True:
            await ws.receive_text()  # keep connection alive
    except:
        ws_manager.disconnect(ws)
        print("WS disconnected")

