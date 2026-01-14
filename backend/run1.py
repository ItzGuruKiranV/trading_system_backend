"""
Single entry point for the trading agent system.
REAL-TIME COMPATIBLE (CSV = candle stream)
"""

# ==================================================
# STANDARD LIBRARY IMPORTS
# ==================================================
import sys
from pathlib import Path
from datetime import datetime

# ==================================================
# PATH SETUP
# ==================================================
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# ==================================================
# INTERNAL IMPORTS (YOUR LOGIC – UNTOUCHED)
# ==================================================
from engine.trend_seed import detect_seed
from engine.swings_detect import (
    market_structure_mapping,
    MASTER_LOG,
    all_legs_event_logs,
)

# ==================================================
# INPUT CSV (1M DATA)
# ==================================================
MINUTE_CSV_PATH = Path(
    r"D:\Trading Project\trading_system_backend\HISTDATA_COM_MT_EURUSD_M12023\DAT_MT_EURUSD_M1_2023.csv"
)

# ==================================================
# SIMPLE CANDLE OBJECT (NO DF)
# ==================================================
class Candle:
    def __init__(self, time, open_, high, low, close):
        self.time = time
        self.open = open_
        self.high = high
        self.low = low
        self.close = close

# ==================================================
# MAIN
# ==================================================
def main():
    print("=" * 60)
    print("Trading Agent - REALTIME MODE (CSV STREAM)")
    print("=" * 60)

    # --------------------------------------------------
    # STEP 1: STREAM 1M CANDLES (NO DF)
    # --------------------------------------------------
    candles_1m = []

    print("\n[Streaming] Reading 1M candles one by one...")

    with open(MINUTE_CSV_PATH, "r", encoding="utf-8") as file:
        for line in file:
            parts = line.strip().split(",")
            if len(parts) < 6:
                continue

            try:
                date_str, time_str, o, h, l, c = parts[:6]
                t = datetime.strptime(
                    date_str + " " + time_str,
                    "%Y.%m.%d %H:%M"
                )

                candle = Candle(
                    time=t,
                    open_=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c),
                )

                candles_1m.append(candle)

            except ValueError:
                continue

    print(f"✅ Stream ready: {len(candles_1m)} candles")

    # --------------------------------------------------
    # STEP 2: BUILD 4H CANDLES MANUALLY (NO DF)
    # --------------------------------------------------
    candles_4h = []
    bucket = []

    for c in candles_1m:
        bucket.append(c)

        if len(bucket) == 240:  # 240 x 1M = 4H
            high = max(x.high for x in bucket)
            low = min(x.low for x in bucket)
            close = bucket[-1].close
            open_ = bucket[0].open
            time = bucket[0].time

            candles_4h.append({
                "time": time,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
            })

            bucket.clear()

    print(f"✅ Built {len(candles_4h)} 4H candles")

    # --------------------------------------------------
    # STEP 3: SEED DETECTION (UNCHANGED LOGIC)
    # --------------------------------------------------
    print("\n[Seed Phase] Running seed detection...")

    import pandas as pd
    df_4h = pd.DataFrame(candles_4h).set_index("time")

    refined_4h_df, trend, bos_time, break_idx, states = detect_seed(df_4h)

    print(f"✅ Seed detected: {trend} at {bos_time}")

    # --------------------------------------------------
    # STEP 4: STREAM 5M CANDLES (NO DF ASSUMPTION)
    # --------------------------------------------------
    candles_5m = []
    bucket = []

    for c in candles_1m:
        if c.time >= refined_4h_df.index[0]:
            bucket.append(c)

            if len(bucket) == 5:
                high = max(x.high for x in bucket)
                low = min(x.low for x in bucket)
                close = bucket[-1].close
                open_ = bucket[0].open
                time = bucket[0].time

                candles_5m.append({
                    "time": time,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                })

                bucket.clear()

    df_5m = pd.DataFrame(candles_5m).set_index("time")

    print(f"✅ Built {len(df_5m)} 5M candles")

    # --------------------------------------------------
    # STEP 5: CALL YOUR CORE STRUCTURE LOGIC (UNCHANGED)
    # --------------------------------------------------
    print("\n[Phase 1] Running structure mapping...")

    event_log = market_structure_mapping(
        df_4h=refined_4h_df,
        df_5m=df_5m,
        trend=trend,
        bos_time=bos_time
    )

    print(f"✅ Events detected: {len(event_log)}")

    # --------------------------------------------------
    # STEP 6: SAVE LOGS (OPTIONAL)
    # --------------------------------------------------
    pd.DataFrame(MASTER_LOG).to_csv("master_log.csv", index=False)
    print(f"✅ master_log.csv saved ({len(MASTER_LOG)} rows)")

# ==================================================
# EXECUTION
# ==================================================
if __name__ == "__main__":
    main()
