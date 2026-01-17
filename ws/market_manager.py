# ws/market_manager.py
from fastapi import WebSocket
from typing import List
import json

class MarketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        # Convert to JSON string once
        text = json.dumps(message)
        
        # Iterate over copy to allow removal during iteration if needed (though disconnect handles removal)
        for connection in self.active_connections[:]: 
            try:
                await connection.send_text(text)
            except:
                # If send fails, assume client disconnected
                self.disconnect(connection)

market_manager = MarketManager()
