# ws/event_manager.py
from fastapi import WebSocket
import asyncio
import json
import threading
import datetime
class EventManager:
    """
    PURE BROADCAST EVENT MANAGER

    - Backend pushes ALL events
    - Frontend filters by symbol / tf
    - No subscriptions
    """

    def __init__(self):
        self.clients: dict[str, set[WebSocket]] = {}  # key = symbol
        self.queue = asyncio.Queue(maxsize=1000)
        self.loop = None
        self.lock = threading.Lock()
        self.worker_task = None

    # -------------------------
    # CONNECTION MANAGEMENT
    # -------------------------

    async def connect(self, ws: WebSocket, symbol: str):
        symbol = symbol.upper()
        with self.lock:
            if symbol not in self.clients:
                self.clients[symbol] = set()
            self.clients[symbol].add(ws)

    def disconnect(self, ws: WebSocket, symbol: str):
        symbol = symbol.upper()
        with self.lock:
            if symbol in self.clients:
                self.clients[symbol].discard(ws)
                num_clients = len(self.clients[symbol])
                print(f"🔴 client-{num_clients} disconnected from marketws for {symbol}")


    # -------------------------
    # LOOP SETUP
    # -------------------------

    def set_loop(self, loop):
        self.loop = loop
        if self.worker_task is None:
            self.worker_task = loop.create_task(self._worker())
            loop.create_task(self._heartbeat()) 
            print("🚀 EventManager worker started")

    # -------------------------
    # BACKGROUND WORKER
    # -------------------------
    async def _heartbeat(self):
        while True:
            await asyncio.sleep(5)  # every 5 seconds
            with self.lock:
                symbols = list(self.clients.keys())
            
            for symbol in symbols:
                await self._broadcast({
                    "symbol": symbol,
                    "type": "heartbeat", 
                    "time": str(datetime.datetime.utcnow())
                })


    async def _worker(self):
        print("🟡 EventManager worker running")
        while True:
            msg = await self.queue.get()
            await self._broadcast(msg)
            self.queue.task_done()

    async def _broadcast(self, message: dict):
        symbol = message.get("symbol")
        if not symbol:
            if message.get("type") == "heartbeat":
                return
            print("⚠️ No symbol in event message, dropping")
            return
        
        symbol = symbol.upper()

        text = json.dumps(message, default=str)
        with self.lock:
            clients = list(self.clients.get(symbol, []))

        for ws in clients:
            # fire-and-forget: one slow client won't block others
            asyncio.create_task(self._safe_send(ws, text, symbol))

    async def _safe_send(self, ws: WebSocket, text: str, symbol: str):
        try:
            await ws.send_text(text)
        except Exception:
            self.disconnect(ws, symbol)



    # -------------------------
    # THREAD-SAFE PUSH
    # -------------------------

    def send_threadsafe(self, message: dict):
        if not self.loop:
            print("⚠️ EventManager loop not set")
            return

        try:
            self.loop.call_soon_threadsafe(
                self.queue.put_nowait,
                message
            )
        except asyncio.QueueFull:
            print("⚠️ Event queue full, dropping message")


# Singleton
event_manager = EventManager()
