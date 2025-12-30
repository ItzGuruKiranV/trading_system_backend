from datetime import datetime
import pandas as pd


def resample_to_4h(data: pd.DataFrame) -> pd.DataFrame:
    """
    Resample 1-minute DataFrame to 4-hour OHLC DataFrame.
    """

    if data.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    df = data.copy()
    df = df.sort_index()

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    df_4h = df.resample("4H", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    )

    df_4h.dropna(how="all", inplace=True)
    return df_4h



def resample_to_5m(data: pd.DataFrame) -> pd.DataFrame:
    """
    Resample 1-minute DataFrame to 5-minute OHLC DataFrame.
    """

    if data.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    df = data.copy()
    df = df.sort_index()

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    df_5m = df.resample("5T", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    )

    df_5m.dropna(how="all", inplace=True)
    return df_5m
