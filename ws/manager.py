# ws/manager.py
import json
from fastapi import WebSocket

class WSManager:
    def __init__(self):
        self.clients = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)


    async def send(self, message: dict):
        data_str = json.dumps(message)
        dead_clients = []

        for ws in self.clients:
            try:
                await ws.send_text(data_str)
            except Exception:
                dead_clients.append(ws)

        for ws in dead_clients:
            self.clients.discard(ws)


ws_manager = WSManager()
