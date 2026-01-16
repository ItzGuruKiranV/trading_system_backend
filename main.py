from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from journal.router import router as journal_router
from calculator.router import router as calculator_router
from candles.router import router as candles_router
from news.router import router as news_router

from ws.candles import router as ws_candles_router
from ws.market_reading import router as market_router

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
app.include_router(candles_router)
app.include_router(news_router)

# WebSocket API
app.include_router(ws_candles_router)
app.include_router(market_router)


@app.get("/")
def root():
    return {"status": "Backend running"}
