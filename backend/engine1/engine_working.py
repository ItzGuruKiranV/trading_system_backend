# from typing import List
# from datetime import datetime
# import pandas as pd
# from candle_stream import Candle
# from state import PairState

# # Engine Logic Imports
# from engine.trend_seed import detect_seed
# from engine.swings_detect import market_structure_mapping

# class PairEngine:
#     def __init__(self, state: PairState):
#         self.state = state
#         self._buffer_4h: List[Candle] = []
        
#         # Historical DataFrames required by logic functions
#         self.df_4h = pd.DataFrame()
#         self.df_5m = pd.DataFrame()

#     def on_candle(self, candle: Candle):
#         """
#         Receive 1-minute candles and accumulate them.
#         When 240 candles (4 hours) are collected, trigger structure updates.
#         """
#         self._buffer_4h.append(candle)

#         if len(self._buffer_4h) == 240:
#             # 1. Convert buffer to DataFrame needed for resampling
#             df_1m_chunk = self._candles_to_df(self._buffer_4h)
            
#             # 2. Update 4H History
#             # Aggregate strictly 240 candles into one 4H candle
#             new_4h_candle = self._aggregate_candles(df_1m_chunk, timeframe="4H")
#             self.df_4h = pd.concat([self.df_4h, new_4h_candle])
            
#             # 3. Update 5M History
#             # Resample the 240 candles into 48 x 5M candles
#             new_5m_candles = df_1m_chunk.resample("5T", label="left", closed="left").agg({
#                 "open": "first",
#                 "high": "max",
#                 "low": "min",
#                 "close": "last"
#             }).dropna()
#             self.df_5m = pd.concat([self.df_5m, new_5m_candles])

#             # 4. Trigger Seeding Logic
#             try:
#                 # detect_seed returns: refined_df, trend, break_time, break_idx, states
#                 # We mainly care about updating the trend in state if valid
#                 result = detect_seed(self.df_4h)
#                 if result:
#                     _, new_trend, _, _, _ = result
#                     self.state.trend_4h = new_trend
#             except ValueError:
#                 # detect_seed raises ValueError if not enough data or no break
#                 pass
#             except Exception as e:
#                 print(f"Error in detect_seed: {e}")

#             # 5. Trigger Market Structure Logic
#             # Only run if we have a trend established (or seed logic allows)
#             try:
#                 # market_structure_mapping(df_4h, df_5m, trend, bos_time, ...)
#                 # Assuming bos_time is tracked in state or we pass the start
#                 # For now, passing state.bos_time_4h or a default
#                 start_time = self.state.bos_time_4h if self.state.bos_time_4h else self.df_4h.index[0]
                
#                 market_structure_mapping(
#                     df_4h=self.df_4h,
#                     df_5m=self.df_5m,
#                     trend=self.state.trend_4h,
#                     bos_time=start_time
#                 )
#             except Exception as e:
#                 print(f"Error in market_structure_mapping: {e}")

#             # Clear the buffer for the next 4H period
#             self._buffer_4h.clear()

#     def emit(self, event: str, time: datetime):
#         """
#         Append an event to state.events.
#         """
#         self.state.events.append({
#             "event": event,
#             "time": time
#         })

#     def _candles_to_df(self, candles: List[Candle]) -> pd.DataFrame:
#         data = [{
#             "time": c.time,
#             "open": c.open,
#             "high": c.high,
#             "low": c.low,
#             "close": c.close
#         } for c in candles]
        
#         df = pd.DataFrame(data)
#         df.set_index("time", inplace=True)
#         return df

#     def _aggregate_candles(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
#         """
#         Aggregates a DataFrame of candles into a single row DataFrame.
#         Used for forming the 4H candle from the buffer.
#         """
#         agg_candle = pd.DataFrame([{
#             "open": df["open"].iloc[0],
#             "high": df["high"].max(),
#             "low": df["low"].min(),
#             "close": df["close"].iloc[-1]
#         }], index=[df.index[0]]) # Use start time of the period
        
#         return agg_candle
