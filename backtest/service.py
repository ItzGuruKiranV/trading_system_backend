from .repository import fetch_trades

def calculate_max_drawdown(trades):
    """
    Calculate max drawdown as the maximum single loss (largest negative P&L) in trades.
    """
    max_loss = 0
    for t in trades:
        if t["pnl"] < 0:
            loss = abs(t["pnl"])
            if loss > max_loss:
                max_loss = loss
    return max_loss


def calculate_stats(trades):
    total_trades = len(trades)
    if total_trades == 0:
        return {}
    
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    
    win_rate = len(wins) / total_trades * 100
    net_profit = sum(t["pnl"] for t in trades)
    average_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    average_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    max_drawdown = calculate_max_drawdown(trades)
    
    return {
        "totalTrades": total_trades,
        "winRate": round(win_rate, 2),
        "netProfit": net_profit,
        "averageWin": round(average_win, 2),
        "averageLoss": round(average_loss, 2),
        "maxDrawdown": max_drawdown
    }

def get_backtest_data(pair: str, year: int):
    trades = fetch_trades(pair, year)
    stats = calculate_stats(trades)
    return {
        "pair": pair,
        "year": year,
        "stats": stats,
        "trades": trades
    }
