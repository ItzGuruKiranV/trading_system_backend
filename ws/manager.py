# ws/manager.py

import json
import asyncio
import threading
from fastapi import WebSocket

class WSManager:
    """
    PURE BROADCAST WebSocket manager

    - Backend pushes EVERYTHING
    - Frontend filters what it wants
    - No subscriptions
    - No symbols
    - No timeframes
    """

    def __init__(self):
        self.clients: dict[str, set[WebSocket]] = {}  # key = symbol
        self.queue: asyncio.Queue = asyncio.Queue()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.lock = threading.Lock()
        self.worker_task = None
        self.heartbeat_task = None
        self.connected_flags: dict[WebSocket, bool] = {}  # track connection state
        self.sent_candles: dict[WebSocket, dict[str, set[int]]] = {}

    # -------------------------
    # CONNECTION MANAGEMENT
    # -------------------------

    async def connect(self, ws: WebSocket, symbol: str):
        symbol = symbol.upper()
        with self.lock:
            if symbol not in self.clients:
                self.clients[symbol] = set()
            self.clients[symbol].add(ws)
            self.connected_flags[ws] = True  
            if ws not in self.sent_candles:
                self.sent_candles[ws] = {"5m": set(), "4h": set()}
            num_clients = len(self.clients[symbol])
            print(f"🟢 client-{num_clients} connected to candlews for {symbol}")
        # NOTE: replay of candles disabled — backend no longer sends candle data
        # This WS manager remains for backward compatibility but will not send
        # any candle messages to clients. Frontend reads candles from CSV.


    def disconnect(self, ws: WebSocket, symbol: str):
        symbol = symbol.upper()
        with self.lock:
            if symbol in self.clients:
                self.clients[symbol].discard(ws)
                self.connected_flags[ws] = False 
                num_clients = len(self.clients[symbol])
                print(f"🔴 client-{num_clients} disconnected from candlews for {symbol}")

    # -------------------------
    # EVENT LOOP SETUP
    # -------------------------

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        print("🟢 WSManager.set_loop called")
        """
        Called ONCE during FastAPI startup.
        Starts background broadcast worker and heartbeat.
        """
        self.loop = loop

        if self.worker_task is None:
            self.worker_task = loop.create_task(self._worker())
            print("🚀 WSManager worker started")

        # No heartbeat task required — backend will not send periodic heartbeats

    # -------------------------
    # HEARTBEAT
    # -------------------------

    # Heartbeat disabled — removed periodic heartbeat sender

    async def _safe_send(self, ws: WebSocket, message: dict, symbol: str):
        try:
            await ws.send_text(json.dumps(message, default=str))
        except Exception:
            self.disconnect(ws, symbol)

    # -------------------------
    # BACKGROUND WORKER
    # -------------------------

    async def _worker(self):
        print("🟡 WSManager worker running")
        while True:
            message = await self.queue.get()
            await self._broadcast(message)
            self.queue.task_done()

    async def _broadcast(self, message: dict):
        """
        Sends message to ONLY relevant symbol clients.
        Expects message to have a 'symbol' key.
        """
        # Drop any candle messages — frontend loads candles from CSV
        if message.get("type") == "candle":
            return

        symbol = message.get("symbol")
        if not symbol:
            print("⚠️ Invalid message, dropping")
            return
        
        symbol = symbol.upper()

        text = json.dumps(message, default=str)

        with self.lock:
            clients = list(self.clients.get(symbol, []))  # ✅ only clients of that symbol

        for ws in clients:
            try:
                if ws not in self.sent_candles:
                    self.sent_candles[ws] = {"5m": set(), "4h": set()}

                # send text to client
                await ws.send_text(text)
            except Exception:
                self.disconnect(ws, symbol)

    # -------------------------
    # THREAD-SAFE PUSH
    # -------------------------

    def send_threadsafe(self, message: dict):
        """
        SAFE to call from:
        - engine threads
        - backtests
        - background workers
        """
        if not self.loop:
            print("⚠️ WSManager loop not set, dropping message")
            return

        try:
            self.loop.call_soon_threadsafe(
                self.queue.put_nowait,
                message
            )
        except asyncio.QueueFull:
            print("⚠️ WS queue full, message dropped")
        except Exception as e:
            print(f"⚠️ WS send error: {e}")


# -------------------------
# SINGLETON INSTANCE
# -------------------------

ws_manager = WSManager()
