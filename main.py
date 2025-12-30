from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from journal.router import router as journal_router
from calculator.router import router as calculator_router
from candles.router import router as candles_router

app = FastAPI(title="Trading Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(journal_router)
app.include_router(calculator_router)
app.include_router(candles_router)

@app.get("/")
def root():
    return {"status": "Backend running"}
