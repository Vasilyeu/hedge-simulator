"""
Module for metrics calculations
"""

import numpy as np
import pandas as pd

from src.core.stats import up_capture, down_capture, alpha, beta, sortino_ratio


def volatility(actives: pd.Series) -> pd.Series:
    """
    Calculates the volatility of a series.
    :param actives: Pandas Series with total value of portfolio actives
    :return: pandas Series with volatility
    """
    return np.log(actives / actives.shift(1)).std() * np.sqrt(len(actives))


def sharpe_ratio(returns, daily_risk_free_rate, days=252):
    """Calculates the sharpe ratio of a series."""
    return (returns.mean() - daily_risk_free_rate) / returns.std() * np.sqrt(days)


def sortino(returns):
    """Calculates the sortino ratio."""
    return sortino_ratio(returns)


def max_drawdown(returns: pd.Series):
    """Calculates the max drawdown of a series."""
    cumulative_return = (returns + 1).cumprod()
    max_return = np.fmax.accumulate(cumulative_return, axis=0)
    return np.min(np.divide((cumulative_return - max_return), max_return))


def upside_capture_ratio(returns: pd.Series, baseline_returns: pd.Series) -> float:
    """Calculates the upside capture ratio of a series."""
    ret = pd.DataFrame({"portfolio": returns, "baseline": baseline_returns}).dropna()
    return up_capture(ret.portfolio, ret.baseline)


def downside_capture_ratio(returns: pd.Series, baseline_returns: pd.Series):
    """Calculates the downside capture ratio of a series."""
    ret = pd.DataFrame({"portfolio": returns, "baseline": baseline_returns}).dropna()
    return down_capture(ret.portfolio, ret.baseline)


def alpha_value(returns: pd.Series, baseline_returns: pd.Series):
    """Calculates portfolio Alpha"""
    ret = pd.DataFrame({"portfolio": returns, "baseline": baseline_returns}).dropna()
    return alpha(ret.portfolio, ret.baseline, risk_free=0.0)


def beta_value(returns: pd.Series, baseline_returns: pd.Series):
    """Calculate portfolio Beta"""
    ret = pd.DataFrame({"portfolio": returns, "baseline": baseline_returns}).dropna()
    return beta(ret.portfolio, ret.baseline, risk_free=0.0)


def tracking_error(returns: pd.Series, baseline_returns: pd.Series):
    """Calculate the tracking error"""
    return np.std((returns - baseline_returns), ddof=1) * np.sqrt(252)
