# ws/event_manager.py
from fastapi import WebSocket
import json

class EventManager:
    def __init__(self):
        self.clients = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.append(ws)
        print(f"🔌 Event WebSocket connected: {len(self.clients)} clients")

    def disconnect(self, ws: WebSocket):
        self.clients.remove(ws)
        print(f"❌ Event WebSocket disconnected: {len(self.clients)} clients left")

    async def broadcast(self, message: dict):
        text = json.dumps(message)
        dead_clients = []

        for ws in self.clients[:]:
            try:
                await ws.send_text(text)
            except Exception:
                dead_clients.append(ws)

        for ws in dead_clients:
            self.disconnect(ws)

# Create a singleton instance
event_manager = EventManager()
