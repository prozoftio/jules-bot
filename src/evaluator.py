import os
import pandas as pd
from src.logger import AsyncTradeLogger

REPORT_PATH = "logs/performance_review.md"

def generate_report():
    logger = AsyncTradeLogger()
    trades = logger.get_all_closed_trades()

    # We must call shutdown so the thread doesn't hang the script since we only needed read access
    logger.shutdown()

    if not trades:
        print("No closed trades found to evaluate.")
        _write_empty_report()
        return

    df = pd.DataFrame(trades)

    # 1. Macro Metrics
    total_pnl = df['pnl'].sum()
    win_rate = (len(df[df['pnl'] > 0]) / len(df)) * 100 if len(df) > 0 else 0

    # Max Drawdown Approximation (Cumulative PnL trough)
    cumulative_pnl = df['pnl'].cumsum()
    peak = cumulative_pnl.expanding(min_periods=1).max()
    drawdown = cumulative_pnl - peak
    max_drawdown = drawdown.min()

    # 2. Strategy Analytics
    regime_pnl = df.groupby('hmm_regime')['pnl'].mean().to_dict()
    avg_pnl_mean_reverting = regime_pnl.get('Mean Reverting', 0.0)
    avg_pnl_trending = regime_pnl.get('Trending', 0.0)
    avg_pnl_volatile = regime_pnl.get('Volatile', 0.0)

    # 3. Execution Quality
    avg_slippage = df['slippage'].mean()
    avg_latency = df['execution_latency_ms'].mean()

    # 4. Failure Log (Top 3 Worst Trades)
    worst_trades = df.nsmallest(3, 'pnl').to_dict('records')

    _write_report(
        total_pnl=total_pnl,
        win_rate=win_rate,
        max_drawdown=max_drawdown,
        avg_pnl_mean_reverting=avg_pnl_mean_reverting,
        avg_pnl_trending=avg_pnl_trending,
        avg_pnl_volatile=avg_pnl_volatile,
        avg_slippage=avg_slippage,
        avg_latency=avg_latency,
        worst_trades=worst_trades
    )

def _write_report(total_pnl, win_rate, max_drawdown, avg_pnl_mean_reverting, avg_pnl_trending, avg_pnl_volatile, avg_slippage, avg_latency, worst_trades):
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)

    markdown_content = f"""# Trading Agent Performance Review

## 1. Macro Metrics
- **Total PnL:** ${total_pnl:.2f}
- **Win Rate:** {win_rate:.2f}%
- **Maximum Drawdown:** ${max_drawdown:.2f}

## 2. Strategy Analytics
- **Average PnL by Regime:**
  - Mean Reverting: ${avg_pnl_mean_reverting:.2f}
  - Trending: ${avg_pnl_trending:.2f}
  - Volatile: ${avg_pnl_volatile:.2f}

## 3. Execution Quality
- **Average Slippage:** ${avg_slippage:.4f}
- **Average Execution Latency:** {avg_latency:.2f} ms

## 4. Failure Log (Top 3 Worst Trades)
"""

    if not worst_trades:
        markdown_content += "No losing trades found.\n"
    else:
        for i, t in enumerate(worst_trades, 1):
            markdown_content += f"{i}. **Trade ID:** {t['trade_id']} | **Pair:** {t['pair']} | **Z-Score:** {t['z_score']:.2f} | **Regime:** {t['hmm_regime']} | **PnL:** ${t['pnl']:.2f}\n"
            markdown_content += f"   - *Details:* Expected Spread: ${t['expected_spread_price']:.4f}, Actual Spread: ${t['actual_spread_price']:.4f}, Slippage: ${t['slippage']:.4f}\n"

    with open(REPORT_PATH, 'w') as f:
        f.write(markdown_content)

    print(f"Report generated successfully at {REPORT_PATH}")

def _write_empty_report():
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, 'w') as f:
        f.write("# Trading Agent Performance Review\n\nNo closed trades available to generate metrics.\n")

if __name__ == "__main__":
    generate_report()
