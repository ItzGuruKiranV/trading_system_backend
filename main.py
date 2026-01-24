from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import asyncio
import threading
from backend import run1

from journal.router import router as journal_router
from calculator.router import router as calculator_router
from news.router import router as news_router

from ws.event_router import router as event_router
from ws.candle_router import router as candle_router
from backtest.router import router as backtest_router




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
app.include_router(backtest_router)
# -------------------------
# STARTUP EVENTS
# -------------------------


# WebSocket API
app.include_router(candle_router)
app.include_router(event_router)


@app.on_event("startup")
async def startup():
    # 1. Give FastAPI event loop to run1 module
    loop = asyncio.get_running_loop()
    run1.event_loop = loop
    
    # 2. Initialize managers
    run1.ws_manager.set_loop(loop)
    run1.event_manager.set_loop(loop)

    PAIRS = ["EURUSD", "GBPJPY"]

    for pair in PAIRS:
        run1.start_engine(pair)

@app.on_event("shutdown")
def stop_engine():
    print("[INFO] FastAPI shutdown detected. Stopping all engines...")
    run1.manager.stop_all_engines()

@app.get("/")
def root():
    return {"status": "Backend running"}
