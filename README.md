## Trading Agent – 4H Swings & Seed Range from 1‑Minute Data

This project takes a 1‑minute EURUSD CSV, resamples it to 4‑hour candles, builds an initial 4H seed range, detects swing highs/lows on 4H, and produces plots.

The entire system is driven from a single entry point: `backend/run.py`. All other files are pure modules (no code that runs on import).

---

### Setup

1. Install Python 3.10+.
2. Install dependencies:

pip install -r requirements.txt---

### How to Run

From the project root:

cd backend
python run.pyThe script will:

1. Open a GUI file picker – select a **1‑minute CSV**.
2. Load the 1‑minute OHLC data.
3. Resample it into 4‑hour candles.
4. Save the 4‑hour CSV next to your input file (same folder, `_4h.csv` suffix).
5. Load the 4‑hour CSV.
6. Build the 4H **seed range** (first 90 candles).
7. Detect leg‑based swing highs/lows on the 4H data.
8. Generate plots (saved in the same folder as your input CSV):

   - `swings.png` – 4H candlesticks + swing highs/lows.
   - `structure_with_seed.png` – 4H candlesticks + seed high/low lines.

---

### CSV Formats

#### 1‑Minute CSV (input to `run.py`)

Format:

date,time,open,high,low,close[,volume...]
2024.01.01,00:00,1.10427,1.10447,1.10342,1.10381- Date: `YYYY.MM.DD`
- Time: `HH:MM` (24‑hour)

#### 4‑Hour CSV (auto‑generated)

Format:

time,open,high,low,close
2024-01-01 00:00:00,1.10427,1.10447,1.10342,1.10381- Time: `YYYY-MM-DD HH:MM:SS`

---

### File Overview

#### `backend/run.py`

Main script. Does:

- GUI file picker for 1‑minute CSV.
- Loads minute data and resamples to 4H.
- Saves 4H CSV and reloads it.
- Builds 4H seed range (first 90 candles).
- Detects leg‑based swings on 4H.
- Calls plotting functions to create PNGs.

#### `backend/engine/__init__.py`

Marks `engine/` as a Python package. No logic.

#### `backend/engine/loader.py`

CSV loading helpers.

- `load_minute_csv(path)` – reads 1‑minute OHLC data into list of dicts.
- `load_4h_csv(path)` – reads 4‑hour OHLC data into list of dicts.

#### `backend/engine/resample.py`

Timeframe conversion and saving.

- `resample_to_4h(data)` – groups 1‑minute candles into 4‑hour candles.
- `save_4h_csv(data_4h, path)` – writes 4‑hour candles to CSV.

#### `backend/engine/state.py`

State container for the 4H logic.

- Holds seed range, trend flags, swing highs/lows, swing midpoint,
  and simple leg‑lock counters.

#### `backend/engine/trend_seed.py`

Trend seeding logic.

- `process_seed_context(candle, state)` – builds the first 90‑candle seed range.
- `seed_trend_from_range(candle, state)` – detects the first close
  above/below the seed range and locks an initial 4H trend.

#### `backend/engine/swings_detect.py`

Leg‑based swing detection on 4H OHLC.

- `momentum_slowing(...)` – checks for body contraction and overlap.
- `detect_swings_leg_based(ohlc_df, ...)` – detects swing highs/lows from
  impulse → pullback → continuation, returns a DataFrame with markers.

#### `backend/engine/plotting.py`

Plotting utilities.

- `plot_swings(candles_4h, swings_df, path)` – candlestick chart with swing highs/lows.
- `plot_structure_with_seed(candles_4h, seed_high, seed_low, path)` –
  candlestick chart with seed high/low lines.