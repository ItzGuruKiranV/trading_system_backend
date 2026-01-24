# ws/router.py
from fastapi import APIRouter, WebSocket
from .manager import ws_manager
import json
import asyncio

router = APIRouter()

@router.websocket("/ws/candles")
async def ws_stream(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            # WAIT FOR INIT/SWITCH MESSAGE
            data = await ws.receive_text()
            init_data = json.loads(data)

            symbol = init_data.get("symbol")
            tf = init_data.get("tf")

            if symbol:
                print(f"🔄 Candle switch/init received: {symbol} {tf}")
                ws_manager.subscribe(ws, symbol, tf)
            else:
                print("⚠️ Received WS message without symbol")

    except Exception as e:
        ws_manager.disconnect(ws)
        print(f"🔴 Candle WS disconnected: {e}")
    finally:
        ws_manager.disconnect(ws)
