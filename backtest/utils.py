def build_backtest_response(trades):
    total = len(trades)
    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "SL"]

    win_rate = round((len(wins) / total) * 100, 2) if total else 0
    net_profit = sum(t["pnl"] for t in trades)

    equity = 10000
    equity_curve = []

    for t in trades:
        equity += t["pnl"]
        equity_curve.append({
            "date": t["trade_date"],
            "equity": equity
        })

    return {
        "system1": {
            "winRate": win_rate,
            "totalTrades": total,
            "profitFactor": round(
                sum(t["pnl"] for t in wins) / abs(sum(t["pnl"] for t in losses)),
                2
            ) if losses else 0,
            "maxDrawdown": 0,
            "netProfit": net_profit,
            "averageWin": round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else 0,
            "averageLoss": round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0,
            "sharpeRatio": 0,
            "trades": [
                {
                    "id": t["id"],
                    "date": t["trade_date"],
                    "pair": t["pair"],
                    "type": "Long" if t["side"] == "BUY" else "Short",
                    "entry": t["entry"],
                    "exit": t["exit"],
                    "pnl": t["pnl"],
                    "result": "Win" if t["result"] == "WIN" else "Loss"
                }
                for t in trades
            ]
        },
        "equityCurve": equity_curve
    }
