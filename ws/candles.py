from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import csv
from datetime import datetime
from pathlib import Path
from datetime import timezone


router = APIRouter()


# =====================================
# CONFIG
# =====================================

SYMBOL = "EURUSD"
SEND_INTERVAL_SECONDS = 1

# 🔥 FIXED PATH
BASE_DIR = Path(__file__).resolve().parent

CSV_MAP = {
    "5m": BASE_DIR / "5m_last_1_month.csv",
    "4h": BASE_DIR / "4h_last_1_month.csv",
}

# =====================================
# LOAD CANDLES
# =====================================

def load_candles(csv_path: Path):
    candles = []

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)

        # auto-detect timestamp column
        ts_col = "timestamp" if "timestamp" in reader.fieldnames else reader.fieldnames[0]

        for row in reader:
            dt = datetime.fromisoformat(row[ts_col]).replace(tzinfo=timezone.utc)

            # 🔥 SNAP TO TF BOUNDARY
            if "4h" in str(csv_path):
                dt = dt.replace(
                    hour=(dt.hour // 4) * 4,
                    minute=0,
                    second=0,
                    microsecond=0
                )

            elif "5m" in str(csv_path):
                dt = dt.replace(
                    minute=(dt.minute // 5) * 5,
                    second=0,
                    microsecond=0
                )
 
            candles.append({
                "timestamp": int(dt.timestamp() * 1000),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0)),
            })

    candles.sort(key=lambda x: x["timestamp"])
    return candles

# =====================================
# WEBSOCKET STREAM
# =====================================

@router.websocket("/ws/candles")
async def candle_ws(websocket: WebSocket):
    await websocket.accept()
    print("🔌 WebSocket connected")

    try:
        sub = await websocket.receive_json()
        symbol = sub.get("symbol")
        tf = sub.get("tf")

        print(f"📩 Subscription: {symbol} {tf}")

        if symbol != SYMBOL or tf not in CSV_MAP:
            await websocket.close(code=1003)
            return

        csv_path = CSV_MAP[tf]
        print(f"📂 Loading candles from: {csv_path}")

        candles = load_candles(csv_path)
        print(f"📊 Loaded {len(candles)} {tf} candles")

        for candle in candles:
            await websocket.send_json({
                "type": "candle",
                "symbol": SYMBOL,
                "tf": tf,
                "timestamp": candle["timestamp"],
                "open": candle["open"],
                "high": candle["high"],
                "low": candle["low"],
                "close": candle["close"],
                "volume": candle["volume"],
            })

            await asyncio.sleep(SEND_INTERVAL_SECONDS)

        while True:
            await asyncio.sleep(30)

    except WebSocketDisconnect:
        print("🔌 WebSocket disconnected")

    except Exception as e:
        print("🔥 WebSocket error:", e)
        await websocket.close()
