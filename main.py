from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import asyncio
import threading
from backend import run1

from journal.router import router as journal_router
from calculator.router import router as calculator_router
from news.router import router as news_router

from ws.market_reading import router as market_router
from ws.candle_router import router as candle_router


app = FastAPI(title="Trading Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST APIs
app.include_router(journal_router)
app.include_router(calculator_router)
app.include_router(news_router)

# -------------------------
# STARTUP EVENTS
# -------------------------


# WebSocket API
app.include_router(candle_router)
app.include_router(market_router)


@app.on_event("startup")
async def startup():
    # give FastAPI event loop to run1 module
    run1.event_loop = asyncio.get_running_loop()

@app.on_event("startup")
async def start_engine():
    # start CSV / realtime engine in background
    threading.Thread(target=run1.main, daemon=True).start()

@app.get("/")
def root():
    return {"status": "Backend running"}
