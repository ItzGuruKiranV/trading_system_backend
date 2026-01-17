from fastapi import APIRouter, WebSocket
import asyncio

router = APIRouter()

# =========================
# DUMMY BOS EVENT (4H)
# =========================

from .market_manager import market_manager

# =========================
# WEBSOCKET ENDPOINT
# =========================

@router.websocket("/ws/market")
async def market_ws(websocket: WebSocket):
    await market_manager.connect(websocket)
    print("🔌 Market WebSocket connected")

    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except Exception as e:
        print("❌ WebSocket disconnected")
        market_manager.disconnect(websocket)
