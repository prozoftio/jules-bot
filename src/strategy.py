import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from statsmodels.tsa.stattools import coint

def calculate_cointegration(series1: pd.Series, series2: pd.Series) -> float:
    """
    Uses statsmodels to verify if two tickers are cointegrated.
    Returns the p-value. A p-value < 0.05 typically indicates cointegration.
    """
    # ensure alignment
    s1, s2 = series1.align(series2, join='inner')

    if len(s1) < 2:
        return 1.0 # Not enough data

    score, pvalue, _ = coint(s1, s2)
    return pvalue

def calculate_z_score(spread: pd.Series, window: int = 60) -> float:
    """
    Calculates the rolling Z-Score of the spread.
    Z = (x_t - mu) / sigma
    """
    if len(spread) < window:
        # Not enough data for rolling window, just use simple mean/std for now
        # or return 0.0 if not strictly enough data
        if len(spread) < 2:
             return 0.0
        mu = spread.mean()
        sigma = spread.std()
    else:
        # Use the last 'window' periods
        recent_spread = spread.tail(window)
        mu = recent_spread.mean()
        sigma = recent_spread.std()

    if sigma == 0:
        return 0.0

    current_spread = spread.iloc[-1]
    z_score = (current_spread - mu) / sigma
    return z_score

class MarketRegimeHMM:
    def __init__(self, n_components: int = 3):
        """
        Initializes the GaussianHMM.
        n_components: Number of hidden states.
        """
        self.n_components = n_components
        self.model = GaussianHMM(n_components=self.n_components, covariance_type="diag", n_iter=100, random_state=42)
        self.state_map = {}

    def fit(self, returns: pd.Series):
        """
        Fits the HMM on historical returns (e.g., SPY) to prevent look-ahead bias.
        """
        # Prepare data for hmmlearn (requires 2D array: n_samples x n_features)
        X = returns.dropna().values.reshape(-1, 1)
        if len(X) < self.n_components:
             return # Not enough data

        self.model.fit(X)
        self._map_states()

    def _map_states(self):
        """
        Maps the abstract HMM states to human-readable regimes based on variance.
        Highest variance -> 'Volatile'
        Lowest variance -> 'Mean Reverting'
        Middle variance -> 'Trending'
        """
        # When covariance_type="diag", covars_ shape is (n_components, n_features)
        # We extract the scalar variance for each state
        variances = np.array([self.model.covars_[i, 0] for i in range(self.n_components)])

        sorted_indices = np.argsort(variances)

        # State with lowest variance
        lowest_var_state = int(sorted_indices[0].item() if isinstance(sorted_indices[0], np.ndarray) else sorted_indices[0])
        # State with middle variance
        middle_var_state = int(sorted_indices[1].item() if isinstance(sorted_indices[1], np.ndarray) else sorted_indices[1])
        # State with highest variance
        highest_var_state = int(sorted_indices[2].item() if isinstance(sorted_indices[2], np.ndarray) else sorted_indices[2])

        self.state_map[lowest_var_state] = 'Mean Reverting'
        self.state_map[middle_var_state] = 'Trending'
        self.state_map[highest_var_state] = 'Volatile'

    def predict(self, recent_returns: pd.Series) -> str:
        """
        Predicts the current state based on recent returns.
        """
        if not self.state_map:
            return "Unknown" # Model not fitted

        X = recent_returns.dropna().values.reshape(-1, 1)
        if len(X) == 0:
            return "Unknown"

        hidden_states = self.model.predict(X)
        current_state = hidden_states[-1] # The state of the most recent observation

        return self.state_map.get(current_state, "Unknown")
