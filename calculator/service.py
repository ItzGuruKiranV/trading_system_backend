def calculate_lot_size(symbol, account_balance, risk_percent, stop_loss_pips):
    if account_balance <= 0:
        raise ValueError("Account balance must be > 0")

    if risk_percent <= 0:
        raise ValueError("Risk percent must be > 0")

    if stop_loss_pips <= 0:
        raise ValueError("Stop loss pips must be > 0")

    risk_amount = account_balance * (risk_percent / 100)

    pip_values = {
        "EURUSD": 10.0,
        "GBPUSD": 10.0,
        "EURAUD": 10.0,
        "GBPJPY": 9.0,
        "XAUUSD": 1.0,
    }

    if symbol not in pip_values:
        raise ValueError("Unsupported symbol")

    pip_value_per_lot = pip_values[symbol]

    lot_size = risk_amount / (stop_loss_pips * pip_value_per_lot)

    return {
        "lot_size": round(lot_size, 2),
        "pip_value_per_lot": pip_value_per_lot,
        "risk_amount": round(risk_amount, 2),
    }
