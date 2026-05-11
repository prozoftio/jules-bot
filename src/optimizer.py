import os
import subprocess
import logging
import sys
from src.backtest import run_backtest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REPORT_PATH = "logs/performance_review.md"

class Optimizer:
    def __init__(self):
        self.report_path = REPORT_PATH

    def _is_git_clean(self) -> bool:
        """
        Step A: Pre-Flight Check. Ensures the working directory is clean.
        """
        try:
            result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True, check=True)
            if result.stdout.strip():
                return False
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Git status check failed: {e}")
            return False

    def _read_report(self) -> str:
        if not os.path.exists(self.report_path):
            logger.error(f"Performance report not found at {self.report_path}")
            return ""
        with open(self.report_path, 'r') as f:
            return f.read()

    def _construct_prompt(self, report_content: str) -> str:
        """
        Step B: Construct the prompt for the Claude CLI.
        """
        prompt = f"""
        You are an autonomous quant trading architect. I am triggering an optimization loop.

        Please read the following performance review of our trading agent over the last period:

        {report_content}

        Your tasks:
        1. Identify the core reason for the failures or suboptimal performance (e.g., Z-score threshold too tight, HMM reacting too slowly or being mis-mapped, or bad cointegration half-life assumption).
        2. Directly modify `src/strategy.py` to fix the issue and improve the logic.

        STRICT CONSTRAINTS:
        - Do NOT modify risk parameters in `src/executor.py` or any other file. Only touch `src/strategy.py`.
        - Do NOT ask for permission. Just write the code and finalize it.
        """
        return prompt

    def _execute_claude(self, prompt: str) -> bool:
        """
        Step C: Execute the Claude CLI via subprocess.
        """
        command = [
            "claude",
            "--bare",
            "--allowedTools", "Read,Write,Bash",
            "-p", prompt
        ]

        logger.info("Triggering Claude CLI optimization...")
        try:
            result = subprocess.run(command, capture_output=True, text=True)
            logger.info("Claude CLI execution finished.")
            logger.debug(f"Claude Output:\n{result.stdout}")
            if result.stderr:
                logger.warning(f"Claude Stderr:\n{result.stderr}")

            # We assume it made changes if the command succeeds.
            return result.returncode == 0
        except FileNotFoundError:
            logger.error("Claude CLI not found. Is it installed and in your PATH?")
            return False
        except Exception as e:
            logger.error(f"Error executing Claude CLI: {e}")
            return False

    def _validate_changes(self) -> bool:
        """
        Step D (Part 1): Run validation gates (pytest and backtest).
        """
        logger.info("Running validation gates on modified strategy...")

        # 1. Pytest
        try:
            logger.info("Running pytest...")
            pytest_result = subprocess.run(['pytest', 'tests/test_strategy.py'], capture_output=True, text=True)
            if pytest_result.returncode != 0:
                logger.error(f"Pytest failed! Reverting changes.\n{pytest_result.stdout}")
                return False
            logger.info("Pytest passed.")
        except Exception as e:
            logger.error(f"Failed to execute pytest: {e}")
            return False

        # 2. Backtest Dry-Run
        try:
            logger.info("Running backtest dry-run...")
            if not run_backtest(days=7):
                logger.error("Backtest failed! Reverting changes.")
                return False
            logger.info("Backtest passed.")
        except Exception as e:
            logger.error(f"Failed to execute backtest: {e}")
            return False

        return True

    def _rollback_changes(self):
        """
        Step D (Part 2a): Rollback if validation fails.
        """
        logger.warning("Rolling back changes to pristine state...")
        try:
            subprocess.run(['git', 'reset', '--hard'], check=True, capture_output=True)
            subprocess.run(['git', 'clean', '-fd'], check=True, capture_output=True)
            logger.info("Rollback complete.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to rollback changes: {e}")

    def _commit_changes(self):
        """
        Step D (Part 2b): Commit if validation passes.
        """
        logger.info("Validation passed. Committing optimized strategy...")
        try:
            subprocess.run(['git', 'add', 'src/strategy.py'], check=True, capture_output=True)
            subprocess.run(['git', 'commit', '-m', 'Auto-optimization: Adjusted parameters based on weekly review'], check=True, capture_output=True)
            logger.info("Optimization successfully committed to repository.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to commit changes: {e}")

    def run_optimization_loop(self):
        """
        Orchestrates the entire self-improving loop.
        """
        logger.info("Starting Autonomous Optimization Loop...")

        # Step A: Pre-Flight
        if not self._is_git_clean():
             logger.error("Working directory is not clean. Aborting optimization to prevent data loss or conflicting states.")
             sys.exit(1)

        # Step B: Construct Prompt
        report_content = self._read_report()
        if not report_content:
             sys.exit(1)

        prompt = self._construct_prompt(report_content)

        # Step C: Execute CLI
        # If Claude fails to run, we just exit.
        if not self._execute_claude(prompt):
             logger.error("Claude execution failed or aborted.")
             # Technically no changes should be committed if it fails, but we'll rollback just in case
             self._rollback_changes()
             sys.exit(1)

        # Step D: Validation & Decision
        if self._validate_changes():
            self._commit_changes()
        else:
            self._rollback_changes()

def main():
    optimizer = Optimizer()
    optimizer.run_optimization_loop()

if __name__ == "__main__":
    main()
