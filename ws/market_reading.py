from fastapi import APIRouter, WebSocket
import asyncio

router = APIRouter()

# =========================
# DUMMY BOS EVENT (4H)
# =========================

DUMMY_MARKET_EVENTS =[
    {
    "symbol": "EURUSD",
    "timeframe": "5m",
    "events": [
      {
        "id": "5m_RETR_20221130_1700",
        "type": "RETRACEMENT",
        "high": 1.04188,
        "low": 1.04029,
        "mid": 1.041085,
        "time_start": "2022-11-30T17:00:00",
        "time_end": "2022-11-30T17:25:00",
        "extend_candles": 5
      }
    ]
  },
  {
    "symbol": "EURUSD",
    "timeframe": "4h",
    "events": [
      {
        "id": "4H_PB_20221207_0000",
        "type": "PULLBACK_CONFIRMED",
        "broken_level": 1.04431,
        "time": "2022-12-07T00:00:00"
      }
    ]
  },
  {
    "symbol": "EURUSD",
    "timeframe": "5m",
    "events": [
      {
        "id": "5m_BOS_20221205_0400",
        "type": "BOS",
        "direction": "BULLISH",
        "broken_level": 1.05680,
        "time": "2022-12-05T04:00:00"
      },
      {
        "id": "5m_CHOCH_20221206_0400",
        "type": "CHOCH",
        "broken_level": 1.05800,
        "time": "2022-12-06T04:00:00"
      }
    ]
  },


  {
    "symbol": "EURUSD",
    "timeframe": "4h",
    "events": [
      {
        "id": "4H_POI_OB_20221214_1200",
        "type": "POI-OB",
        "trend": "BULLISH",
        "time_start": "2022-12-14T12:00:00",
        "time_end": "2022-12-14T16:00:00",
        "low": 1.06206,
        "high": 1.06950
      }
    ]
  },

  {
    "symbol": "EURUSD",
    "timeframe": "4H",
    "events": [
      {
        "id": "4H_BOS_20221205_0400",
        "type": "BOS",
        "direction": "BULLISH",
        "broken_level": 1.05680,
        "time": "2022-12-05T04:00:00"
      },
      {
        "id": "4H_CHOCH_20221206_0400",
        "type": "CHOCH",
        "broken_level": 1.05800,
        "time": "2022-12-06T04:00:00"
      }
    ]
  },
  {
    "symbol": "EURUSD",
    "timeframe": "4H",
    "events": [
      {
        "id": "4H_POI_LIQ_20221207_0400",
        "type": "POI-LIQ",
        "price": 1.05680,
        "time": "2022-12-07T04:00:00"
      },
      {
        "id": "4H_POI_LIQ_20221208_0400",
        "type": "POI-LIQ",
        "price": 1.05800,
        "time": "2022-12-08T04:00:00"
      }
    ]
  }

]


# =========================
# WEBSOCKET ENDPOINT
# =========================

@router.websocket("/ws/market")
async def market_ws(websocket: WebSocket):
    await websocket.accept()
    print("🔌 Market WebSocket connected")

    try:
        for idx, event in enumerate(DUMMY_MARKET_EVENTS):
            await websocket.send_json(event)
            print(f"📩 Sent market event {idx + 1}/{len(DUMMY_MARKET_EVENTS)}")

            # wait 20 seconds before sending next
            await asyncio.sleep(20)

        print("✅ All events sent, closing WebSocket")
        await websocket.close()

    except Exception as e:
        print("❌ WebSocket error:", e)
        await websocket.close()