# Setup Guide: Self-Improving Trading Agent

This guide will walk you through setting up and running the autonomous, self-improving quantitative trading system.

## 1. Prerequisites

Before starting, ensure you have the following installed on your local machine:
- **Python 3.11+**
- **Git**
- **Claude CLI** (Authenticated globally. See [Anthropic Documentation](https://docs.anthropic.com/en/docs/developer-tools/claude-cli) if you haven't set this up yet).
- **Alpaca Paper Trading Account** (You can sign up for free at [Alpaca Markets](https://app.alpaca.markets/brokerage/new-account)).

## 2. Environment Setup

1. **Clone the Repository:**
   ```bash
   git clone <your-repository-url>
   cd <your-repository-directory>
   ```

2. **Create a Virtual Environment (Recommended):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## 3. Configuration

The system is hardcoded to strictly use the **Alpaca Paper API** (`https://paper-api.alpaca.markets`) for safety. However, you still need to provide your API keys via environment variables.

1. Obtain your Paper API Key and Secret Key from the Alpaca Dashboard.
2. Export them in your terminal session:
   ```bash
   export APCA_API_KEY_ID="your_paper_api_key_here"
   export APCA_API_SECRET_KEY="your_paper_api_secret_here"
   ```

## 4. Running the System

The system operates in a multi-phase loop.

### Phase A: Execution (The Live Agent)
The executor runs your ML strategy (HMM Regime Detection + Pairs Trading), manages risk (5% position limit, -2% daily circuit breaker), and executes trades via Alpaca. It logs telemetry asynchronously to SQLite.

```bash
python -m src.executor
```
*Note: This script should ideally be run on a schedule (e.g., cron job every hour during market hours).*

### Phase B: Evaluation (The Analyst)
After trading hours or at the end of the week, generate a performance review. This script reads the SQLite database and generates `logs/performance_review.md`.

```bash
python -m src.evaluator
```

### Phase C: Optimization (The Self-Improving Loop)
This is where the magic happens. The optimizer reads the performance review and programmatically invokes the local Claude CLI to optimize the strategy logic in `src/strategy.py`.

**CRITICAL:** Ensure your Git working directory is completely clean before running this command, or the optimizer will abort to prevent data loss.

```bash
# Ensure clean working directory
git status

# Run the optimizer
python -m src.optimizer
```

The optimizer will:
1. Invoke Claude to modify `strategy.py`.
2. Run validation gates (`pytest` and `backtest`).
3. If successful, automatically `git commit` the optimized strategy. If it fails, it will aggressively rollback (`git reset --hard` & `git clean -fd`) to protect the repository.

## 5. Testing and Development

To manually run the validation tests that the optimizer uses:
```bash
pytest tests/
```
