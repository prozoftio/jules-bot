import sqlite3
import threading
import queue
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = "logs/trades.db"

class AsyncTradeLogger:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.log_queue = queue.Queue()
        self.stop_event = threading.Event()

        # Initialize schema
        self._init_db()

        # Start background worker thread
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades_log (
                    trade_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    pair TEXT,
                    action TEXT,
                    hmm_regime TEXT,
                    z_score REAL,
                    expected_spread_price REAL,
                    actual_spread_price REAL,
                    leg1_fill_price REAL,
                    leg2_fill_price REAL,
                    slippage REAL,
                    execution_latency_ms REAL,
                    pnl REAL,
                    status TEXT
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to initialize SQLite database: {e}")

    def _worker(self):
        """Background thread that consumes the queue and writes to SQLite."""
        # Using a new connection per thread is required by sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        while not self.stop_event.is_set():
            try:
                # Wait for an item with a timeout so we can check the stop event
                task = self.log_queue.get(timeout=1.0)

                if task is None:
                    continue

                task_type, data = task

                if task_type == 'open':
                    cursor.execute('''
                        INSERT INTO trades_log (
                            trade_id, timestamp, pair, action, hmm_regime, z_score,
                            expected_spread_price, actual_spread_price,
                            leg1_fill_price, leg2_fill_price, slippage,
                            execution_latency_ms, pnl, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        data['trade_id'], data['timestamp'], data['pair'], data['action'],
                        data['hmm_regime'], data['z_score'], data['expected_spread_price'],
                        data['actual_spread_price'], data['leg1_fill_price'], data['leg2_fill_price'],
                        data['slippage'], data['execution_latency_ms'], 0.0, 'OPEN'
                    ))
                elif task_type == 'close':
                    cursor.execute('''
                        UPDATE trades_log
                        SET status = 'CLOSED', pnl = ?
                        WHERE trade_id = ?
                    ''', (data['pnl'], data['trade_id']))

                conn.commit()
                self.log_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in AsyncTradeLogger worker thread: {e}")

        conn.close()

    def log_trade_open(self, trade_id: str, pair: str, action: str, hmm_regime: str,
                       z_score: float, expected_spread: float, actual_spread: float,
                       leg1_price: float, leg2_price: float, slippage: float, latency_ms: float):
        """
        Asynchronously logs a new open trade to SQLite.
        """
        data = {
            'trade_id': trade_id,
            'timestamp': datetime.utcnow().isoformat() + "Z",
            'pair': pair,
            'action': action,
            'hmm_regime': hmm_regime,
            'z_score': z_score,
            'expected_spread_price': expected_spread,
            'actual_spread_price': actual_spread,
            'leg1_fill_price': leg1_price,
            'leg2_fill_price': leg2_price,
            'slippage': slippage,
            'execution_latency_ms': latency_ms
        }
        self.log_queue.put(('open', data))

    def log_trade_close(self, trade_id: str, pnl: float):
        """
        Asynchronously marks a trade as CLOSED and records the realized PnL.
        """
        data = {
            'trade_id': trade_id,
            'pnl': pnl
        }
        self.log_queue.put(('close', data))

    def get_recent_trades(self, limit: int = 100):
        """
        Synchronously retrieves the most recent trades. Useful for evaluator.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM trades_log ORDER BY timestamp DESC LIMIT ?', (limit,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve recent trades: {e}")
            return []

    def get_all_closed_trades(self):
        """
        Synchronously retrieves all closed trades. Useful for evaluator.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades_log WHERE status = 'CLOSED' ORDER BY timestamp DESC")
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve closed trades: {e}")
            return []

    def shutdown(self):
        """
        Gracefully stops the worker thread, ensuring all pending logs are written.
        """
        self.stop_event.set()
        self.worker_thread.join(timeout=5.0)
