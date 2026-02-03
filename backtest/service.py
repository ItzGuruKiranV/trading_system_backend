from .repository import fetch_trades

def get_backtest_data(pair: str, year: str):
    trades = fetch_trades(pair, year)

    if not trades:
        return None

    total_trades = len(trades)
    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "SL"]

    win_rate = round((len(wins) / total_trades) * 100, 2)
    net_pnl = sum(t["pnl"] for t in trades)

    def build_type_stats(trade_type: str):
        filtered = [t for t in trades if t["trade_type"] == trade_type]
        if not filtered:
            return {
                "trades": 0,
                "win": 0,
                "loss": 0,
                "win_rate": 0
            }

        w = len([t for t in filtered if t["result"] == "WIN"])
        l = len([t for t in filtered if t["result"] == "SL"])

        return {
            "trades": len(filtered),
            "win": w,
            "loss": l,
            "win_rate": round((w / len(filtered)) * 100, 2)
        }

    return {
        "win_rate": win_rate,
        "total_trades": total_trades,
        "net_pnl": net_pnl,
        "pullback": build_type_stats("PULLBACK"),
        "choch": build_type_stats("CHOCH"),
        "recent_ten_trades": sorted(
            trades,
            key=lambda t: t["trade_date"],
            reverse=True
        )[:10]
    }
