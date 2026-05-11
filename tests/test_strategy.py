import pytest
import pandas as pd
import numpy as np
from src.strategy import calculate_z_score, calculate_cointegration, MarketRegimeHMM

def test_calculate_z_score():
    # Create mock spread data
    spread = pd.Series(np.random.normal(0, 1, 100))

    # Calculate Z-score
    z_score = calculate_z_score(spread, window=60)

    # Assert it returns a float
    assert isinstance(z_score, float)

    # Test edge case: not enough data
    short_spread = pd.Series([1.0])
    z_score_short = calculate_z_score(short_spread, window=60)
    assert z_score_short == 0.0

def test_market_regime_hmm():
    hmm = MarketRegimeHMM(n_components=3)

    # Mock returns
    returns = pd.Series(np.random.normal(0.001, 0.02, 100))

    # Fit model
    hmm.fit(returns)

    # Predict state
    state = hmm.predict(returns)

    # Assert state is a valid string mapped to our regimes
    assert isinstance(state, str)
    assert state in ['Mean Reverting', 'Trending', 'Volatile', 'Unknown']

def test_calculate_cointegration():
    # Mock cointegrated series
    np.random.seed(42)
    s1 = pd.Series(np.random.normal(0, 1, 100))
    s2 = s1 + pd.Series(np.random.normal(0, 0.1, 100))

    p_value = calculate_cointegration(s1, s2)
    assert isinstance(p_value, float)
    assert p_value >= 0.0 and p_value <= 1.0
