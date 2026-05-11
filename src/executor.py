import os
import logging
import uuid
import time
from datetime import datetime, timedelta
import pandas as pd

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.requests import StockLatestQuoteRequest

from .strategy import calculate_z_score, MarketRegimeHMM
from .logger import AsyncTradeLogger

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

class TradingExecutor:
    def __init__(self):
        # Always use paper trading URL
        self.api_key = os.environ.get("APCA_API_KEY_ID")
        self.api_secret = os.environ.get("APCA_API_SECRET_KEY")

        if not self.api_key or not self.api_secret:
            logger.warning("Alpaca API credentials not found in environment variables.")

        # Initialize Alpaca Trading Client (Paper=True strictly enforced)
        self.client = TradingClient(self.api_key, self.api_secret, paper=True)

        # Initialize Alpaca Data Client
        self.data_client = StockHistoricalDataClient(self.api_key, self.api_secret)

        # Initialize Async Logger
        self.db_logger = AsyncTradeLogger()

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

    def check_circuit_breaker(self) -> bool:
        """
        Checks if the daily PnL has dropped below -2%.
        If so, halts trading.
        """
        try:
            account = self.client.get_account()
            equity = float(account.equity)
            last_equity = float(account.last_equity)

            if last_equity == 0:
                 return False

            pnl_pct = (equity - last_equity) / last_equity

            if pnl_pct < -0.02:
                logger.critical(f"CIRCUIT BREAKER TRIGGERED: Daily PnL is {pnl_pct*100:.2f}%. Trading Halted.")
                return True
            return False
        except Exception as e:
            logger.error(f"Error checking circuit breaker: {e}")
            # If we can't verify safety, default to unsafe
            return True

    def calculate_position_size(self, portfolio_value: float, risk_limit_pct: float = 0.05) -> float:
        """
        Calculates the maximum dollar amount to risk for a single trade.
        Strict 5% risk limit guardrail.
        """
        # Hard cap the risk limit at 5% just in case
        actual_risk_limit = min(risk_limit_pct, 0.05)
        return portfolio_value * actual_risk_limit

    def fetch_historical_data(self, symbol: str, days: int = 60) -> pd.DataFrame:
        """
        Fetches historical hourly data for a given symbol.
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        request_params = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TimeFrame.Hour,
            start=start_date,
            end=end_date
        )

        try:
            bars = self.data_client.get_stock_bars(request_params)
            df = bars.df
            # Dataframes from alpaca have multi-index (symbol, timestamp)
            if not df.empty:
               # Get just the single symbol data
               df = df.xs(symbol, level='symbol')
            return df
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return pd.DataFrame()

    def get_latest_spread(self, symbol: str) -> float:
        """
        Fetches the latest quote and calculates the bid-ask spread.
        """
        request_params = StockLatestQuoteRequest(symbol_or_symbols=[symbol])
        try:
            quotes = self.data_client.get_stock_latest_quote(request_params)
            quote = quotes[symbol]
            spread = quote.ask_price - quote.bid_price
            return spread
        except Exception as e:
            logger.error(f"Error fetching quote for {symbol}: {e}")
            return float('inf')

    def execute_trade(self, symbol: str, side: OrderSide, notional_amount: float):
        """
        Executes a trade via Alpaca API with a notional amount limit.
        Does not check spread here to avoid partial executions.
        Returns the order object if successful.
        """
        try:
            if self.check_circuit_breaker():
                 return None

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

def main():
    logger.info("Initializing Trading Executor...")
    executor = TradingExecutor()

    if executor.check_circuit_breaker():
         return

    # Configuration
    spy_symbol = "SPY"
    pair_symbol1 = "KO"
    pair_symbol2 = "PEP"
    days_history = 60
    min_spread_threshold = 0.05

    logger.info("Starting Warm-up Phase: Fetching 60 days of historical data...")
    spy_data = executor.fetch_historical_data(spy_symbol, days=days_history)
    s1_data = executor.fetch_historical_data(pair_symbol1, days=days_history)
    s2_data = executor.fetch_historical_data(pair_symbol2, days=days_history)

    if spy_data.empty or s1_data.empty or s2_data.empty:
         logger.error("Failed to fetch historical data for warm-up. Exiting.")
         return

    # Calculate returns for SPY for HMM
    spy_returns = spy_data['close'].pct_change().dropna()

    # Train HMM
    logger.info("Training HMM on SPY returns...")
    hmm = MarketRegimeHMM(n_components=3)

    # Fix Look-ahead bias: Fit HMM on historical data up to previous timestamp
    # Predict the state for the current timestamp
    hmm.fit(spy_returns.iloc[:-1])

    current_regime = hmm.predict(spy_returns)
    logger.info(f"Current Market Regime: {current_regime}")

    # Calculate Z-Score for pair
    # Assuming spread is log(price1) - log(price2) or just price1 - price2 for simplicity
    # Align dataframes
    s1_close, s2_close = s1_data['close'].align(s2_data['close'], join='inner')
    spread = s1_close - s2_close

    z_score = calculate_z_score(spread, window=60)
    logger.info(f"Current Z-Score for {pair_symbol1}-{pair_symbol2}: {z_score:.4f}")

    # Logic Gate
    # To manage state, we would typically check our current positions.
    # For now, we will query Alpaca to see if we have open positions for these symbols.
    try:
        open_positions = executor.client.get_all_positions()
        open_symbols = [p.symbol for p in open_positions]
        has_open_position = pair_symbol1 in open_symbols or pair_symbol2 in open_symbols
    except Exception as e:
        logger.error(f"Failed to fetch open positions: {e}")
        has_open_position = False

    if current_regime == 'Mean Reverting':
         if abs(z_score) > 2.0 and not has_open_position:
              logger.info("Signal: OPEN TRADE (HMM=Mean Reverting, |Z| > 2.0)")

              # Execute trade logic (Multi-leg pairs execution)
              # If Z-score is negative (spread < mean): buy leg 1, short leg 2
              # If Z-score is positive (spread > mean): short leg 1, buy leg 2
              # For paper trading purposes with notional, shorting might have constraints.
              # Assuming standard long/short execution.
              test_notional = 10.0

              # Validate spreads for BOTH legs before execution to prevent unhedged positions
              spread1 = executor.get_latest_spread(pair_symbol1)
              spread2 = executor.get_latest_spread(pair_symbol2)

              if spread1 > min_spread_threshold or spread2 > min_spread_threshold:
                  logger.warning(f"SpreadTooWide: Spreads ({spread1:.4f}, {spread2:.4f}) exceed threshold {min_spread_threshold:.4f}. Skipping trade.")
              else:
                  trade_id = str(uuid.uuid4())
                  action_str = "BUY_SPREAD" if z_score < -2.0 else "SELL_SPREAD"

                  # Calculate expected net spread price right before execution
                  try:
                      quote1 = executor.data_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=[pair_symbol1]))[pair_symbol1]
                      quote2 = executor.data_client.get_stock_latest_quote(StockLatestQuoteRequest(symbol_or_symbols=[pair_symbol2]))[pair_symbol2]
                      expected_price_leg1 = quote1.ask_price if z_score < -2.0 else quote1.bid_price
                      expected_price_leg2 = quote2.bid_price if z_score < -2.0 else quote2.ask_price
                      expected_spread_price = expected_price_leg1 - expected_price_leg2
                  except Exception as e:
                      logger.warning(f"Failed to get expected spread price: {e}")
                      expected_spread_price = 0.0

                  leg1_side = OrderSide.BUY if z_score < -2.0 else OrderSide.SELL
                  leg2_side = OrderSide.SELL if z_score < -2.0 else OrderSide.BUY

                  start_time = time.time()

                  # Execute Leg 1
                  order1 = executor.execute_trade(
                      symbol=pair_symbol1,
                      side=leg1_side,
                      notional_amount=test_notional
                  )

                  # Execute Leg 2
                  order2 = executor.execute_trade(
                      symbol=pair_symbol2,
                      side=leg2_side,
                      notional_amount=test_notional
                  )

                  latency_ms = (time.time() - start_time) * 1000

                  if order1 and order2:
                      # Get filled prices (sleep briefly to allow fills to process on paper, or assume market orders fill instantly)
                      time.sleep(1) # Simple delay for paper fill propagation
                      try:
                          pos1 = executor.client.get_open_position(pair_symbol1)
                          pos2 = executor.client.get_open_position(pair_symbol2)
                          fill_leg1 = float(pos1.avg_entry_price)
                          fill_leg2 = float(pos2.avg_entry_price)
                          actual_spread_price = fill_leg1 - fill_leg2
                          slippage = abs(expected_spread_price - actual_spread_price)

                          executor.db_logger.log_trade_open(
                              trade_id=trade_id,
                              pair=f"{pair_symbol1}/{pair_symbol2}",
                              action=action_str,
                              hmm_regime=current_regime,
                              z_score=z_score,
                              expected_spread=expected_spread_price,
                              actual_spread=actual_spread_price,
                              leg1_price=fill_leg1,
                              leg2_price=fill_leg2,
                              slippage=slippage,
                              latency_ms=latency_ms
                          )
                          logger.info(f"Asynchronously logged OPEN trade {trade_id} to SQLite.")
                      except Exception as e:
                          logger.error(f"Failed to calculate actual fill prices and log trade: {e}")

         elif abs(z_score) < 0.5 and has_open_position:
              logger.info("Signal: CLOSE TRADE (Take Profit / Exit, |Z| < 0.5)")
              try:
                  if pair_symbol1 in open_symbols:
                      logger.info(f"Closing position for {pair_symbol1}...")
                      executor.client.close_position(symbol_or_asset_id=pair_symbol1)
                  if pair_symbol2 in open_symbols:
                      logger.info(f"Closing position for {pair_symbol2}...")
                      executor.client.close_position(symbol_or_asset_id=pair_symbol2)
              except Exception as e:
                  logger.error(f"Error closing positions: {e}")
              finally:
                  # For Phase 3, we simulate logging the close. To accurately map PnL, we'd need to match the open trade_id.
                  # Since we don't store open trade_ids in memory here between executions, we will look up the most recent OPEN trade.
                  try:
                      recent_open_trades = [t for t in executor.db_logger.get_recent_trades() if t['status'] == 'OPEN']
                      if recent_open_trades:
                          last_trade = recent_open_trades[0]
                          # Mock PnL calculation for now until we fully process closed positions
                          mock_pnl = 5.0 # In a real scenario, calculate from execution fill vs entry
                          executor.db_logger.log_trade_close(trade_id=last_trade['trade_id'], pnl=mock_pnl)
                          logger.info(f"Asynchronously logged CLOSE trade {last_trade['trade_id']} to SQLite.")
                  except Exception as db_e:
                      logger.error(f"Error logging trade close: {db_e}")

         else:
              logger.info(f"No action taken. Z-Score: {z_score:.4f}, Has Position: {has_open_position}")
    else:
         logger.info(f"HMM is not 'Mean Reverting' (Current: {current_regime}).")
         if has_open_position and abs(z_score) < 0.5:
              logger.info("Signal: CLOSE TRADE (Take Profit / Exit, |Z| < 0.5) outside of regime.")
              try:
                  if pair_symbol1 in open_symbols:
                      executor.client.close_position(symbol_or_asset_id=pair_symbol1)
                  if pair_symbol2 in open_symbols:
                      executor.client.close_position(symbol_or_asset_id=pair_symbol2)
              except Exception as e:
                  logger.error(f"Error closing positions: {e}")
              finally:
                  try:
                      recent_open_trades = [t for t in executor.db_logger.get_recent_trades() if t['status'] == 'OPEN']
                      if recent_open_trades:
                          last_trade = recent_open_trades[0]
                          mock_pnl = 5.0
                          executor.db_logger.log_trade_close(trade_id=last_trade['trade_id'], pnl=mock_pnl)
                          logger.info(f"Asynchronously logged CLOSE trade {last_trade['trade_id']} to SQLite.")
                  except Exception as db_e:
                      logger.error(f"Error logging trade close: {db_e}")
         else:
              logger.info("Staying in cash.")

    # Ensure background thread shuts down and flushes queue
    executor.db_logger.shutdown()

if __name__ == "__main__":
    main()
