"""
Single entry point for the trading agent system.
"""

# ==================================================
# STANDARD LIBRARY IMPORTS
# ==================================================
import os
import sys
from pathlib import Path
from datetime import datetime

# ==================================================
# THIRD-PARTY IMPORTS
# ==================================================
import pandas as pd

# ==================================================
# PATH SETUP
# ==================================================
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
sys.path.insert(0, str(BASE_DIR))

# ==================================================
# INTERNAL ENGINE IMPORTS
# ==================================================
from engine.resample import resample_to_4h , resample_to_5m
from engine.trend_seed import detect_seed
from engine_2.resample import resample_to_30m  
from engine_2.structure_mapping_30m import market_structure_mapping_30m
from engine.swings_detect import market_structure_mapping_dynamic

# ==================================================
# FIXED INPUT FILE
# ==================================================
MINUTE_CSV_PATH = Path(
    r"D:\Trading Project\trading_system_backend\HISTDATA_COM_MT_EURUSD_M12023\DAT_MT_EURUSD_M1_2023.csv"
)

# ==================================================
# MAIN ENTRY POINT
# ==================================================
def main():
    print("=" * 60)
    print("Trading Agent - Market Structure Analysis")
    print("=" * 60)

    # --------------------------------------------------
    # STEP 1: LOAD 1-MIN DATA (INLINE, NO LOADER)
    # --------------------------------------------------
    print("\n[Step 1] Loading 1-minute data...")

    rows = []
    try:
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
                    rows.append({
                        "time": t,
                        "open": float(o),
                        "high": float(h),
                        "low": float(l),
                        "close": float(c),
                    })
                except ValueError:
                    continue

        df_1m = pd.DataFrame(rows)
        df_1m.set_index("time", inplace=True)
        df_1m.sort_index(inplace=True)

        print(f"✅ Loaded {len(df_1m)} minute candles")

    except Exception as e:
        print(f"❌ Error loading minute data: {e}")
        return

    # --------------------------------------------------
    # STEP 2: RESAMPLE TO 4-HOUR (IN MEMORY)
    # --------------------------------------------------
    print("\n[Step 2] Resampling to 4-hour candles...")
    try:
        df_4h = resample_to_4h(df_1m)
        print(f"✅ Resampled to {len(df_4h)} 4-hour candles")
        df_5m = resample_to_5m(df_1m)
        print(f"✅ Resampled to {len(df_5m)} 5-minute candles")
        df_30m = resample_to_30m(df_1m)
        print(f"✅ Resampled to {len(df_30m)} 30-minute candles")
    except Exception as e:
        print(f"❌ Error during resampling: {e}")
        return

    # --------------------------------------------------
    # STEP 3: SEED LOGIC (PRE-PHASE-1)
    # --------------------------------------------------
    # ---------------------------------------------
    # SEED DETECTION ON 4H
    # ---------------------------------------------
    print("\n[Seed Phase] Running seed detection on 4H...")

    refined_4h_df, trend, bos_time, break_idx, states = detect_seed(df_4h)
    print(f"✅ Seed detected: {trend} at {bos_time}")

    
    # ---------------------------------------------
    # HARD ALIGNMENT (SAFETY)
    # ---------------------------------------------
    refined_4h_df = refined_4h_df.sort_index()
    first_4h_time = refined_4h_df.index[0]

    # ---------------------------------------------
    # ALIGN 5M DATA TO 4H SEED
    # ---------------------------------------------
    print("\n[Alignment] Aligning 5M data to 4H structure...")

    refined_5m_df = df_5m[df_5m.index >= first_4h_time]
    refined_30m_df = df_30m[df_30m.index >= first_4h_time]

    print(f"4H candles after seed : {len(refined_4h_df)}")
    print(f"5M candles after seed : {len(refined_5m_df)}")
    print(f"30M candles after seed : {len(refined_30m_df)}")



    # --------------------------------------------------
    # STEP 4: RULE-BASED SWING DETECTION (PHASE 1)
    # --------------------------------------------------print("\n[Phase 1] Running rule-based structure mapping...")
    print("\n[Phase 1] Running rule-based structure mapping... 1 ")
    try:
        # Sanity checks
        if refined_4h_df.empty or refined_5m_df.empty:
            raise ValueError("Refined dataframes are empty")

        # Run logging phase
        market_structure_mapping_dynamic(df_4h=refined_4h_df, df_5m=refined_5m_df, trend=trend, bos_time=bos_time)

        # Plotting phase  
        from swings_detect import EVENT_LOG
        from swings_plot import swings_plotter  # Import the log
        plotter = swings_plotter(refined_4h_df)
        for state in EVENT_LOG:
            plotter.plot_single_state(state)


    except Exception as e:
        print(f"\n❌ Error in dynamic swings mapping: {e}")



    print("\n[Phase 1] Running rule-based structure mapping... 2 ")
    try:
        # Sanity checks
        if refined_4h_df.empty or refined_5m_df.empty or refined_30m_df.empty:
            raise ValueError("Refined dataframes are empty")

        # --------------------------------------------------
        # CALL STRUCTURE LOGIC WITH 30M ADDED
        # --------------------------------------------------
        market_structure_mapping_30m(
            df_4h=refined_4h_df,
            df_5m=refined_5m_df,
            df_30m=refined_30m_df,
            trend=trend,
            bos_time=bos_time,
        )
    except Exception as e:
        print(f"\n❌ Error in structure mapping: {e}")








# ==================================================
# SCRIPT EXECUTION
# ==================================================
if __name__ == "__main__":
    main()
