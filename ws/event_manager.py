# ws/event_manager.py
from fastapi import WebSocket
import asyncio
import json
import threading
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
            num_clients = len(self.clients[symbol])
            print(f"🟢 client-{num_clients} connected to marketws for {symbol}")


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
            print("🚀 EventManager worker started")

    # -------------------------
    # BACKGROUND WORKER
    # -------------------------
    async def _worker(self):
        print("🟡 EventManager worker running")
        while True:
            msg = await self.queue.get()
            await self._broadcast(msg)
            self.queue.task_done()

    async def _broadcast(self, message: dict):
        symbol = message.get("symbol")

        if not symbol:
            print("⚠️ No symbol in event message, dropping")
            return

        symbol = symbol.upper()
        timeframe = message.get("timeframe")
        events = message.get("events") if isinstance(message.get("events"), list) else []

        # 🔍 Proper debug logging (reflects REAL structure)
        evt_count = len(events)
        print(f"[EVENT_BCAST] {symbol} {timeframe} -> {evt_count} events")

        for e in events:
            print(
                f"   • type={e.get('type')} | id={e.get('id')} | time={e.get('time')}"
            )

        # Convert to text once
        text = json.dumps(message, default=str)

        # Copy clients safely
        with self.lock:
            clients = list(self.clients.get(symbol, []))

        # 🚀 Fire-and-forget sending
        for ws in clients:
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
