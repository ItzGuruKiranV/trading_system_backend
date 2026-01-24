# ws/manager.py
import json
import asyncio
import threading
from fastapi import WebSocket

class WSManager:
    def __init__(self):
        self.clients = {}  # Map: WebSocket -> symbol
        self.queue = asyncio.Queue()
        self.lock = threading.Lock()
        self.loop = None
        self.worker_task = None

    async def connect(self, ws: WebSocket, symbol: str = None):
        await ws.accept()
        with self.lock:
            self.clients[ws] = symbol
        print(f"[BUY] Candle WS connected: {len(self.clients)} clients (Symbol: {symbol})")

    def disconnect(self, ws: WebSocket):
        with self.lock:
            if ws in self.clients:
                del self.clients[ws]
        print(f"[SELL] Candle WS disconnected: {len(self.clients)} clients left")

    def has_active_clients(self, symbol: str) -> bool:
        """Check if any client is currently subscribed to this symbol."""
        with self.lock:
            for sub_data in self.clients.values():
                if isinstance(sub_data, dict):
                    if sub_data.get("symbol") == symbol:
                        return True
                elif sub_data == symbol:
                    return True
            return False

    def subscribe(self, ws: WebSocket, symbol: str, tf: str = None):
        """Update the symbol and timeframe for an existing connection."""
        with self.lock:
            if ws in self.clients:
                self.clients[ws] = {"symbol": symbol, "tf": tf}
                print(f"🔄 Client subscribed to: {symbol} ({tf})")
        

    def set_loop(self, loop):
        """
        Sets the event loop and starts the worker if not already running.
        Must be called from the async context (or where loop is available).
        """
        self.loop = loop
        if self.worker_task is None:
            self.worker_task = self.loop.create_task(self._worker())
            print(f"[DONE] WSManager worker started on loop: {self.loop}")

    async def _worker(self):
        """Background worker that broadcasts events from the queue."""
        print(f"[DONE] WSManager worker RUNNING on loop: {asyncio.get_running_loop()}")
        while True:
            message = await self.queue.get()
            await self._broadcast(message)
            self.queue.task_done()

    async def _broadcast(self, message: dict):
        """Broadcast to ALL clients (timeframe/pair independent flow)."""
        text = json.dumps(message, default=str)
        
        with self.lock:
            items = list(self.clients.items())
            
        for ws, sub_data in items:
            try:
                await ws.send_text(text)
            except Exception:
                self.disconnect(ws)

    def send_threadsafe(self, message: dict):
        """
        Thread-safe way to enqueue an event.
        Can be called from any thread, including backtesting loop.
        """
        if self.loop is None:
            print("[WARN] WSManager loop not set! Cannot send message.")
            return

        try:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, message)
        except asyncio.QueueFull:
            print("[WARN] WSManager queue full! Dropping message.")
        except Exception as e:
            print(f"[WARN] WSManager send_threadsafe error: {e}")


# Singleton
ws_manager = WSManager()
