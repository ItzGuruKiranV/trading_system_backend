from fastapi import APIRouter, HTTPException
import requests, os
from datetime import datetime

router = APIRouter(prefix="/api/news", tags=["News"])

API_KEY = os.getenv("FINNHUB_API_KEY")

@router.get("")
def get_news():
    if not API_KEY:
        raise HTTPException(status_code=500, detail="FINNHUB_API_KEY missing")

    url = "https://finnhub.io/api/v1/news"
    params = {"category": "forex", "token": API_KEY}

    res = requests.get(url, params=params)
    if res.status_code != 200:
        raise HTTPException(status_code=500, detail="Finnhub API failed")

    news = []
    for item in res.json():
        headline = item.get("headline")
        ts = item.get("datetime")

        if not headline or not ts:
            continue

        dt = datetime.fromtimestamp(ts)
        print(item)
        news.append({
            "id": str(item.get("id")),
            "date": dt.strftime("%Y-%m-%d"),
            "time": dt.strftime("%H:%M"),
            "currency": "USD",        # ✅ important
            "impact": "MEDIUM",
            "title": headline,
            "actual": None,
            "forecast": None,
            "previous": None,
        })

    return news
