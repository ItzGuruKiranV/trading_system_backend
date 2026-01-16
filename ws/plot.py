import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# ===============================
# CONFIG
# ===============================
CSV_FILE = r"C:\Gurukiran\projects\trading_system\trading_system_backend\ws\4h_last_1_month.csv"
TITLE = "EURUSD 4h Candles"

# ===============================
# LOAD DATA
# ===============================
df = pd.read_csv(CSV_FILE)

# Handle pandas index timestamp
ts_col = "timestamp" if "timestamp" in df.columns else df.columns[0]
df[ts_col] = pd.to_datetime(df[ts_col])

df.set_index(ts_col, inplace=True)
df.sort_index(inplace=True)

# ===============================
# PLOT
# ===============================
fig, ax = plt.subplots(figsize=(15, 7))

width = 0.6
for i, (ts, row) in enumerate(df.iterrows()):
    open_, high, low, close = row["open"], row["high"], row["low"], row["close"]

    # wick
    ax.plot([i, i], [low, high])

    # body
    color = "green" if close >= open_ else "red"
    lower = min(open_, close)
    height = abs(close - open_)

    ax.add_patch(Rectangle(
        (i - width / 2, lower),
        width,
        height,
    ))

ax.set_title(TITLE)
ax.set_xlabel("Candles")
ax.set_ylabel("Price")

ax.grid(True)
plt.tight_layout()
plt.show()
