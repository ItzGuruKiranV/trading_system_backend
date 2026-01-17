# ws/event_router.py
from fastapi import APIRouter, WebSocket
import asyncio
from .event_manager import event_manager  # your new event manager

router = APIRouter()

# =========================
# EVENTS WEBSOCKET ENDPOINT
# =========================

@router.websocket("/ws/events")
async def events_ws(websocket: WebSocket):
    await event_manager.connect(websocket)
    print("🔌 Event WebSocket connected")

    try:
        while True:
            await websocket.receive_text()  # keep connection alive
    except Exception:
        event_manager.disconnect(websocket)
        print("❌ Event WebSocket disconnected")


