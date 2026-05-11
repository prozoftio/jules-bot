import os
import logging
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# Hardcoded strictly to Paper Trading
PAPER_URL = "https://paper-api.alpaca.markets"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class TradingExecutor:
    def __init__(self):
        # Always use paper trading URL
        api_key = os.environ.get("APCA_API_KEY_ID")
        api_secret = os.environ.get("APCA_API_SECRET_KEY")

        if not api_key or not api_secret:
            logger.warning("Alpaca API credentials not found in environment variables.")

        # We ensure paper=True for safety as well.
        self.client = TradingClient(api_key, api_secret, paper=True)

        # We can also override the URL just to be absolutely certain we're on paper
        # Though alpaca-py uses paper=True to route to paper-api.alpaca.markets
        # we will ensure it doesn't accidentally hit production.

    def get_portfolio_value(self) -> float:
        """
        Retrieves the current total portfolio value.
        """
        try:
            account = self.client.get_account()
            return float(account.portfolio_value)
        except Exception as e:
            logger.error(f"Error fetching portfolio value: {e}")
            return 0.0

    def calculate_position_size(self, portfolio_value: float, risk_limit_pct: float = 0.05) -> float:
        """
        Calculates the maximum dollar amount to risk for a single trade.
        Strict 5% risk limit guardrail.
        """
        # Hard cap the risk limit at 5% just in case
        actual_risk_limit = min(risk_limit_pct, 0.05)
        return portfolio_value * actual_risk_limit

    def execute_trade(self, symbol: str, side: OrderSide, notional_amount: float):
        """
        Executes a trade via Alpaca API with a notional amount limit.
        """
        try:
            portfolio_value = self.get_portfolio_value()
            max_allowed_risk = self.calculate_position_size(portfolio_value)

            if notional_amount > max_allowed_risk:
                logger.warning(f"Trade rejected: Notional amount {notional_amount} exceeds maximum allowed risk {max_allowed_risk} (5% of portfolio).")
                return None

            order_data = MarketOrderRequest(
                symbol=symbol,
                notional=notional_amount,
                side=side,
                time_in_force=TimeInForce.DAY
            )

            logger.info(f"Submitting {side} order for {notional_amount} of {symbol}...")
            order = self.client.submit_order(order_data=order_data)
            logger.info(f"Order submitted successfully. Order ID: {order.id}")
            return order
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            return None

def stub_hmm_regime_detection():
    """
    Stub for HMM regime detection.
    Will eventually return the current market regime (e.g., 'trending', 'mean_reverting', 'volatile').
    """
    # Hardcoded for Phase 1 testing
    return 'mean_reverting'

def stub_pairs_trading_signal():
    """
    Stub for Statistical Arbitrage (Pairs Trading) signal.
    Will eventually return the Z-score and trading signal.
    """
    # Hardcoded for Phase 1 testing
    return {
        'signal': 'buy',
        'symbol1': 'AAPL',
        'symbol2': 'MSFT',
        'z_score': -2.5
    }

def main():
    logger.info("Initializing Trading Executor...")
    executor = TradingExecutor()

    # 1. HMM Regime Detection
    regime = stub_hmm_regime_detection()
    logger.info(f"Current Market Regime: {regime}")

    # 2. If in a favorable regime, check pairs trading signal
    if regime == 'mean_reverting':
        signal_data = stub_pairs_trading_signal()
        logger.info(f"Generated Trade Signal: {signal_data}")

        if signal_data['signal'] == 'buy':
            # Example execution: Buying the spread
            # In a real pairs trade, we would buy one and short the other.
            # For this stub, we'll just demonstrate the execution plumbing with one leg.

            # Use a safe notional amount for testing (e.g., $10)
            test_notional = 10.0
            executor.execute_trade(
                symbol=signal_data['symbol1'],
                side=OrderSide.BUY,
                notional_amount=test_notional
            )

if __name__ == "__main__":
    main()
