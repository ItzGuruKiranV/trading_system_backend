# ws/router.py
from fastapi import APIRouter, WebSocket
from .manager import ws_manager
import json
import asyncio

router = APIRouter()

@router.websocket("/ws/candles/{pair}")
async def ws_stream(ws: WebSocket, pair: str):
    pair = pair.upper()
    await ws.accept()
    await ws_manager.connect(ws, pair)
    num_clients = len(ws_manager.clients.get(pair, []))
    print(f"🟢 client-{num_clients} connected to candlews for {pair}")

    try:
        while True:
            await ws.receive_text()

        # while True:
        #     # WAIT FOR INIT/SWITCH MESSAGE
        #     data = await ws.receive_text()
        #     init_data = json.loads(data)

        #     symbol = init_data.get("symbol")
        #     tf = init_data.get("tf")

        #     if symbol:
        #         print(f"🔄 Candle switch/init received: {symbol} {tf}")
        #         ws_manager.subscribe(ws, symbol, tf)
        #     else:
        #         print("⚠️ Received WS message without symbol")

    except Exception as e:
        print(f"🔴 Candle WS disconnected: {e}")
    finally:
        ws_manager.disconnect(ws, pair)