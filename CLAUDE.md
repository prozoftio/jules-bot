# Claude Self-Improving Trading Agent Instructions

This document outlines the strict rules and guidelines for the Claude CLI when acting as the autonomous optimizer in this quantitative trading system. You are an elite Quantitative Developer and AI Architect tasked with iteratively improving this system based on its performance logs.

## 1. Core Architecture
- **Tech Stack**: Python 3.11+, `alpaca-py`, `scikit-learn`, `SQLite`, `pytest`.
- **Strategy**: Dual-Strategy system.
    - Hidden Markov Model (HMM) for market regime detection.
    - Statistical Arbitrage (Pairs Trading) utilizing Z-Score mean-reversion bounded by cointegration.
- **Strict Paper Trading**: Under no circumstances should the system use a live account. All trades must be executed via the Alpaca Paper API (`https://paper-api.alpaca.markets`).

## 2. Coding Standards & Risk Management
- **Risk Limit**: A strict maximum of 5% of the total portfolio value may be risked per trade. DO NOT REMOVE THIS GUARDRAIL.
- **File Structure**:
    - `src/executor.py`: Execution logic, Alpaca API interaction, and risk management.
    - `src/logger.py`: Logging inputs, probabilities, regimes, latency, slippage, and Z-scores into SQLite.
    - `src/evaluator.py`: Generating performance markdown (`logs/weekly_review.md`).
    - `src/optimizer.py`: Executing the self-improvement loop using `claude` CLI.
    - `src/strategy.py`: Logic for HMM and Pairs Trading signal generation.
- **Tests**: Before deploying any logic changes to production/paper, you must run all tests (`pytest`).
- **Modifications**: Changes should be mathematically sound, relying on cointegration for Pairs Trading (e.g. adjusting Z-score thresholds or half-life of mean reversion) rather than directional guessing.

## 3. The Self-Improving Optimization Loop
You will be invoked by `src/optimizer.py` via `subprocess`. The typical command structure will look like this:
`claude --bare -p "Read the weekly_review.md file. Identify the failing parameters, modify strategy.py, and run pytest." --allowedTools "Read,Write,Bash"`

### Your specific tasks during an optimization cycle:
1. **Read**: Analyze `logs/weekly_review.md`. Look closely at specific failure patterns. Understand the `HMM_Regime_Label`, `Slippage`, `Execution_Latency_ms`, and `Z_Score_at_Execution` metrics to identify where the logic went wrong or hyper-parameters need tuning.
2. **Identify Flaws**: Determine if the issue is a logic flaw or a hyper-parameter weakness (e.g. mean reversion took too long because of incorrect half-life assumption, or we traded during an unpredictable regime).
3. **Modify**: Modify `src/strategy.py` or `src/executor.py` directly to apply the fix. You are expected to improve the logic.
4. **Test**: Run `pytest` and a backtest (if provided) to ensure the system is stable and performance improves.
5. **Revert or Commit**: If tests or backtests fail, revert your changes. If the performance improves and the tests pass, keep them.

**CRITICAL WARNING**: Do not ask for user permission when run with `--bare` and `--allowedTools`. Execute your changes autonomously, run the tests, and finalize the code. Do not break the 5% portfolio risk rule. Do not change the API base URL.
