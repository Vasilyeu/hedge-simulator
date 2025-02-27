"""Statistics functions."""
import math
from collections import OrderedDict
from functools import partial
from math import pow
from sys import float_info

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike
from scipy import optimize, stats

from src.core.utils import (
    _adjust_returns,
    _aligned_series,
    _create_binary_vectorized_roll_function,
    _create_unary_vectorized_roll_function,
    down,
    nanmean,
    nanmin,
    nanstd,
    roll,
    up,
)

from .periods import (
    ANNUALIZATION_FACTORS,
    APPROX_BDAYS_PER_MONTH,
    APPROX_BDAYS_PER_YEAR,
    DAILY,
    MONTHLY,
    QUARTERLY,
    WEEKLY,
    YEARLY,
)


def annualization_factor(period, annualization):
    """Return annualization factor from period entered or if a custom value is passed in.

    Parameters
    ----------
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'Monthly':12
            'weekly': 52
            'daily': 252

    annualization : int, optional
        Used to suppress default values available in `period` to convert
        returns into annual returns. Value should be the annual frequency of
        `returns`.

    Returns:
    -------
    annualization_factor : float
    """
    return ANNUALIZATION_FACTORS[period] if annualization is None else annualization


def simple_returns(prices):
    """Compute simple returns from a timeseries of prices.

    Parameters
    ----------
    prices : pd.Series, pd.DataFrame or np.ndarray
        Prices of assets in wide-format, with assets as columns,
        and indexed by datetimes.

    Returns:
    -------
    returns : array-like
        Returns of assets in wide-format, with assets as columns,
        and index coerced to be tz-aware.
    """
    if isinstance(prices, pd.DataFrame | pd.Series):
        out = prices.pct_change().iloc[1:]
    else:
        # Assume np.ndarray
        out = np.diff(prices, axis=0)

        # Silence divide error warnings
        with np.errstate(divide="ignore", invalid="ignore"):
            np.divide(out, prices[:-1], out=out)

    return out


def cum_returns(returns, starting_value=0, out=None) -> ArrayLike:
    """Compute cumulative returns from simple returns.

    Parameters
    ----------
    returns : pd.Series, np.ndarray, or pd.DataFrame
        Returns of the strategy as a percentage, noncumulative.
         - Time series with decimal returns.
         - Example::

            2015-07-16   -0.012143
            2015-07-17    0.045350
            2015-07-20    0.030957
            2015-07-21    0.004902

         - Also accepts two dimensional data. In this case, each column is
           cumulated.

    starting_value : float, optional
       The starting returns.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.

    Returns:
    -------
    cumulative_returns : array-like
        Series of cumulative returns.
    """
    if len(returns) < 1:
        return returns.copy()

    nanmask = np.isnan(returns)
    if np.any(nanmask):
        returns = returns.copy()
        returns[nanmask] = 0

    allocated_output = out is None
    if allocated_output:
        out = np.empty_like(returns)

    np.add(returns, 1, out=out)
    out.cumprod(axis=0, out=out)

    if starting_value == 0:
        np.subtract(out, 1, out=out)
    else:
        np.multiply(out, starting_value, out=out)

    if allocated_output:
        if returns.ndim == 1 and isinstance(returns, pd.Series):
            out = pd.Series(out, index=returns.index)
        elif isinstance(returns, pd.DataFrame):
            out = pd.DataFrame(
                out,
                index=returns.index,
                columns=returns.columns,
            )

    return out


def cum_returns_final(returns, starting_value=0):
    """Compute total returns from simple returns.

    Parameters
    ----------
    returns : pd.DataFrame, pd.Series, or np.ndarray
       Noncumulative simple returns of one or more timeseries.
    starting_value : float, optional
       The starting returns.

    Returns:
    -------
    total_returns : pd.Series, np.ndarray, or float
        If input is 1-dimensional (a Series or 1D numpy array), the result is a
        scalar.

        If input is 2-dimensional (a DataFrame or 2D numpy array), the result
        is a 1D array containing cumulative returns for each column of input.
    """
    if len(returns) == 0:
        return np.nan

    result = (returns + 1).prod() if isinstance(returns, pd.DataFrame) else np.nanprod(returns + 1, axis=0)

    if starting_value == 0:
        result -= 1
    else:
        result *= starting_value

    return result


def aggregate_returns(returns, convert_to):
    """Aggregates returns by week, month, or year.

    Parameters
    ----------
    returns : pd.Series
       Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    convert_to : str
        Can be 'weekly', 'monthly', or 'yearly'.

    Returns:
    -------
    aggregated_returns : pd.Series
    """

    def cumulate_returns(x):
        return cum_returns(x).iloc[-1]

    if convert_to == WEEKLY:
        grouping = [lambda x: x.year, lambda x: x.isocalendar()[1]]
    elif convert_to == MONTHLY:
        grouping = [lambda x: x.year, lambda x: x.month]
    elif convert_to == QUARTERLY:
        grouping = [lambda x: x.year, lambda x: int(math.ceil(x.month / 3.0))]
    elif convert_to == YEARLY:
        grouping = [lambda x: x.year]
    else:
        raise ValueError(f"convert_to must be {WEEKLY}, {MONTHLY} or {YEARLY}")

    return returns.groupby(grouping).apply(cumulate_returns)


def drawdown_series(returns, out=None):
    """Computes the series of drawdowns of a strategy.

    Parameters
    ----------
    returns : pd.Series, pd.DataFrame or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.

    Returns:
    -------
    drawdown_series :  pd.Series, pd.DataFrame or np.ndarray

    Note:
    -----
    See https://en.wikipedia.org/wiki/Drawdown_(economics) for more details.
    """
    allocated_output = out is None
    if allocated_output:
        out = np.empty(
            (returns.shape[0] + 1,) + returns.shape[1:],
            dtype="float64",
        )

    returns_1d = returns.ndim == 1

    if len(returns) < 1:
        out[()] = np.nan
        if returns_1d:
            out = out.item()
        return out

    returns_array = np.asanyarray(returns)

    out[0] = start = 100
    cum_returns(returns_array, starting_value=start, out=out[1:])

    max_return = np.fmax.accumulate(out, axis=0)

    np.divide((out - max_return), max_return, out=out)

    if returns.ndim == 1 and isinstance(returns, pd.Series):
        out = pd.Series(out[1:], index=returns.index)
    elif isinstance(returns, pd.DataFrame):
        out = pd.DataFrame(
            out[1:],
            index=returns.index,
            columns=returns.columns,
        )

    return out


def max_drawdown(returns, out=None):
    """Determines the maximum drawdown of a strategy.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.

    Returns:
    -------
    max_drawdown : float, np.array or pd.Series

    Note:
    -----
    See https://en.wikipedia.org/wiki/Drawdown_(economics) for more details.
    """
    allocated_output = out is None
    if allocated_output:
        out = np.empty(returns.shape[1:])

    returns_1d = returns.ndim == 1

    if len(returns) < 1:
        out[()] = np.nan
        if returns_1d:
            out = out.item()
        return out

    nanmin(drawdown_series(returns), axis=0, out=out)
    if returns_1d:
        out = out.item()
    elif allocated_output and isinstance(returns, pd.DataFrame):
        out = pd.Series(out, index=returns.columns)

    return out


roll_max_drawdown = _create_unary_vectorized_roll_function(max_drawdown)


def annual_return(returns, period=DAILY, annualization=None):
    """Determines the mean annual growth rate of returns.
    
    This is equivilent to the compound annual growth rate.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Periodic returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    annualization : int, optional
        Used to suppress default values available in `period` to convert
        returns into annual returns. Value should be the annual frequency of
        `returns`.

    Returns:
    -------
    annual_return : float
        Annual Return as CAGR (Compounded Annual Growth Rate).

    """
    if len(returns) < 1:
        return np.nan

    ann_factor = annualization_factor(period, annualization)
    num_years = len(returns) / ann_factor
    # Pass array to ensure index -1 looks up successfully.
    ending_value = cum_returns_final(returns, starting_value=1)

    return ending_value ** (1 / num_years) - 1


def cagr(returns, period=DAILY, annualization=None):
    """Compute compound annual growth rate.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    annualization : int, optional
        Used to suppress default values available in `period` to convert
        returns into annual returns. Value should be the annual frequency of
        `returns`.
        - See full explanation in :func:`~empyrical.stats.annual_return`.

    Returns:
    -------
    cagr : float
        The CAGR value.

    """
    return annual_return(returns, period, annualization)


roll_cagr = _create_unary_vectorized_roll_function(cagr)


def annual_volatility(returns, period=DAILY, alpha=2.0, annualization=None, out=None):
    """Determines the annual volatility of a strategy.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Periodic returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'Monthly':12
            'weekly': 52
            'daily': 252

    alpha : float, optional
        Scaling relation (Levy stability exponent).
    annualization : int, optional
        Used to suppress default values available in `period` to convert
        returns into annual returns. Value should be the annual frequency of
        `returns`.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.

    Returns:
    -------
    annual_volatility : float
    """
    allocated_output = out is None
    if allocated_output:
        out = np.empty(returns.shape[1:])

    returns_1d = returns.ndim == 1

    if len(returns) < 2:
        out[()] = np.nan
        if returns_1d:
            out = out.item()
        return out

    ann_factor = annualization_factor(period, annualization)
    nanstd(returns, ddof=1, axis=0, out=out)
    out = np.multiply(out, ann_factor ** (1.0 / alpha), out=out)
    if returns_1d:
        out = out.item()
    return out


roll_annual_volatility = _create_unary_vectorized_roll_function(
    annual_volatility,
)


def calmar_ratio(returns, period=DAILY, annualization=None):
    """Determines the Calmar ratio, or drawdown ratio, of a strategy.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    annualization : int, optional
        Used to suppress default values available in `period` to convert
        returns into annual returns. Value should be the annual frequency of
        `returns`.


    Returns:
    -------
    calmar_ratio : float
        Calmar ratio (drawdown ratio) as float. Returns np.nan if there is no
        calmar ratio.

    Note:
    -----
    See https://en.wikipedia.org/wiki/Calmar_ratio for more details.
    """
    max_dd = max_drawdown(returns=returns)
    if max_dd < 0:
        temp = annual_return(returns=returns, period=period, annualization=annualization) / abs(max_dd)
    else:
        return np.nan

    if np.isinf(temp):
        return np.nan

    return temp


def omega_ratio(
    returns,
    risk_free=0.0,
    required_return=0.0,
    annualization=APPROX_BDAYS_PER_YEAR,
):
    """Determines the Omega ratio of a strategy.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    risk_free : int, float
        Constant risk-free return throughout the period
    required_return : float, optional
        Minimum acceptance return of the investor. Threshold over which to
        consider positive vs negative returns. It will be converted to a
        value appropriate for the period of the returns. E.g. An annual minimum
        acceptable return of 100 will translate to a minimum acceptable
        return of 0.018.
    annualization : int, optional
        Factor used to convert the required_return into a daily
        value. Enter 1 if no time period conversion is necessary.

    Returns:
    -------
    omega_ratio : float

    Note:
    -----
    See https://en.wikipedia.org/wiki/Omega_ratio for more details.

    """
    if len(returns) < 2:
        return np.nan

    if annualization == 1:
        return_threshold = required_return
    elif required_return <= -1:
        return np.nan
    else:
        return_threshold = (1 + required_return) ** (1.0 / annualization) - 1

    returns_less_thresh = returns - risk_free - return_threshold

    numer = sum(returns_less_thresh[returns_less_thresh > 0.0])
    denom = -1.0 * sum(returns_less_thresh[returns_less_thresh < 0.0])

    if denom > 0.0:
        return numer / denom
    else:
        return np.nan


def sharpe_ratio(returns, risk_free=0, period=DAILY, annualization=None, out=None):
    """Determines the Sharpe ratio of a strategy.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    risk_free : int, float
        Constant daily risk-free return throughout the period.
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    annualization : int, optional
        Used to suppress default values available in `period` to convert
        returns into annual returns. Value should be the annual frequency of
        `returns`.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.

    Returns:
    -------
    sharpe_ratio : float
        nan if insufficient length of returns or if if adjusted returns are 0.

    Note:
    -----
    See https://en.wikipedia.org/wiki/Sharpe_ratio for more details.

    """
    allocated_output = out is None
    if allocated_output:
        out = np.empty(returns.shape[1:])

    return_1d = returns.ndim == 1

    if len(returns) < 2:
        out[()] = np.nan
        if return_1d:
            out = out.item()
        return out

    returns_risk_adj = np.asanyarray(_adjust_returns(returns, risk_free))
    ann_factor = annualization_factor(period, annualization)

    # Silence divide error warnings
    with np.errstate(divide="ignore", invalid="ignore"):
        np.multiply(
            np.divide(
                nanmean(returns_risk_adj, axis=0),
                nanstd(returns_risk_adj, ddof=1, axis=0),
                out=out,
            ),
            np.sqrt(ann_factor),
            out=out,
        )

    if return_1d:
        out = out.item()

    return out


roll_sharpe_ratio = _create_unary_vectorized_roll_function(sharpe_ratio)


def sortino_ratio(
    returns,
    required_return=0,
    period=DAILY,
    annualization=None,
    out=None,
    _downside_risk=None,
):
    """Determines the Sortino ratio of a strategy.

    Parameters
    ----------
    returns : pd.Series or np.ndarray or pd.DataFrame
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    required_return: float / series
        minimum acceptable return
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    annualization : int, optional
        Used to suppress default values available in `period` to convert
        returns into annual returns. Value should be the annual frequency of
        `returns`.
    _downside_risk : float, optional
        The downside risk of the given inputs, if known. Will be calculated if
        not provided.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.

    Returns:
    -------
    sortino_ratio : float or pd.Series

        depends on input type
        series ==> float
        DataFrame ==> pd.Series

    Note:
    -----
    See `<https://www.sunrisecapital.com/wp-content/uploads/2014/06/Futures_
    Mag_Sortino_0213.pdf>`__ for more details.

    """
    allocated_output = out is None
    if allocated_output:
        out = np.empty(returns.shape[1:])

    return_1d = returns.ndim == 1

    if len(returns) < 2:
        out[()] = np.nan
        if return_1d:
            out = out.item()
        return out

    adj_returns = np.asanyarray(_adjust_returns(returns, required_return))

    ann_factor = annualization_factor(period, annualization)

    average_annual_return = nanmean(adj_returns, axis=0) * ann_factor
    annualized_downside_risk = (
        _downside_risk if _downside_risk is not None else downside_risk(returns, required_return, period, annualization)
    )

    # Silence divide error warnings
    with np.errstate(divide="ignore", invalid="ignore"):
        np.divide(average_annual_return, annualized_downside_risk, out=out)

    if return_1d:
        out = out.item()
    elif isinstance(returns, pd.DataFrame):
        out = pd.Series(out)

    return out


roll_sortino_ratio = _create_unary_vectorized_roll_function(sortino_ratio)


def downside_risk(returns, required_return=0, period=DAILY, annualization=None, out=None):
    """Determines the downside deviation below a threshold.

    Parameters
    ----------
    returns : pd.Series or np.ndarray or pd.DataFrame
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    required_return: float / series
        minimum acceptable return
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    annualization : int, optional
        Used to suppress default values available in `period` to convert
        returns into annual returns. Value should be the annual frequency of
        `returns`.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.

    Returns:
    -------
    downside_deviation : float or pd.Series
        depends on input type
        series ==> float
        DataFrame ==> pd.Series

    Note:
    -----
    See `<https://www.sunrisecapital.com/wp-content/uploads/2014/06/Futures_
    Mag_Sortino_0213.pdf>`__ for more details, specifically why using the
    standard deviation of the negative returns is not correct.
    """
    allocated_output = out is None
    if allocated_output:
        out = np.empty(returns.shape[1:])

    returns_1d = returns.ndim == 1

    if len(returns) < 1:
        out[()] = np.nan
        if returns_1d:
            out = out.item()
        return out

    ann_factor = annualization_factor(period, annualization)

    downside_diff = np.clip(
        _adjust_returns(
            np.asanyarray(returns),
            np.asanyarray(required_return),
        ),
        -np.inf,
        0,
    )

    np.square(downside_diff, out=downside_diff)
    nanmean(downside_diff, axis=0, out=out)
    np.sqrt(out, out=out)
    np.multiply(out, np.sqrt(ann_factor), out=out)

    if returns_1d:
        out = out.item()
    elif isinstance(returns, pd.DataFrame):
        out = pd.Series(out, index=returns.columns)
    return out


roll_downside_risk = _create_unary_vectorized_roll_function(downside_risk)


def excess_sharpe(returns, factor_returns, out=None):
    """Determines the Excess Sharpe of a strategy.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns: float / series
        Benchmark return to compare returns against.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.

    Returns:
    -------
    excess_sharpe : float

    Note:
    -----
    The excess Sharpe is a simplified Information Ratio that uses
    tracking error rather than "active risk" as the denominator.
    """
    allocated_output = out is None
    if allocated_output:
        out = np.empty(returns.shape[1:])

    returns_1d = returns.ndim == 1

    if len(returns) < 2:
        out[()] = np.nan
        if returns_1d:
            out = out.item()
        return out

    active_return = _adjust_returns(returns, factor_returns)
    tracking_error = np.nan_to_num(nanstd(active_return, ddof=1, axis=0))

    # Silence divide warnings
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.divide(
            nanmean(active_return, axis=0, out=out),
            tracking_error,
            out=out,
        )

    if returns_1d:
        out = out.item()
    return out


roll_excess_sharpe = _create_binary_vectorized_roll_function(excess_sharpe)


def alpha_beta(
    returns,
    factor_returns,
    risk_free=0.0,
    period=DAILY,
    annualization=None,
    out=None,
):
    """Calculates annualized alpha and beta.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns : pd.Series
         Daily noncumulative returns of the factor to which beta is
         computed. Usually a benchmark such as the market.
         - This is in the same style as returns.
    risk_free : int, float, optional
        Constant risk-free return throughout the period. For example, the
        interest rate on a three month us treasury bill.
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    annualization : int, optional
        Used to suppress default values available in `period` to convert
        returns into annual returns. Value should be the annual frequency of
        `returns`.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.

    Returns:
    -------
    alpha : float
    beta : float
    """
    returns, factor_returns = _aligned_series(returns, factor_returns)

    return alpha_beta_aligned(
        returns,
        factor_returns,
        risk_free=risk_free,
        period=period,
        annualization=annualization,
        out=out,
    )


def roll_alpha_beta(returns, factor_returns, window=10, **kwargs):
    """Computes alpha and beta over a rolling window.

    Parameters
    ----------
    lhs : array-like
        The first array to pass to the rolling alpha-beta.
    rhs : array-like
        The second array to pass to the rolling alpha-beta.
    window : int
        Size of the rolling window in terms of the periodicity of the data.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.
    **kwargs
        Forwarded to :func:`~empyrical.alpha_beta`.
    """
    returns, factor_returns = _aligned_series(returns, factor_returns)

    return roll_alpha_beta_aligned(returns, factor_returns, window=window, **kwargs)


def alpha_beta_aligned(
    returns,
    factor_returns,
    risk_free=0.0,
    period=DAILY,
    annualization=None,
    out=None,
):
    """Calculates annualized alpha and beta.

    If they are pd.Series, expects returns and factor_returns have already
    been aligned on their labels.  If np.ndarray, these arguments should have
    the same shape.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns : pd.Series or np.ndarray
         Daily noncumulative returns of the factor to which beta is
         computed. Usually a benchmark such as the market.
         - This is in the same style as returns.
    risk_free : int, float, optional
        Constant risk-free return throughout the period. For example, the
        interest rate on a three month us treasury bill.
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    annualization : int, optional
        Used to suppress default values available in `period` to convert
        returns into annual returns. Value should be the annual frequency of
        `returns`.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.

    Returns:
    -------
    alpha : float
    beta : float
    """
    if out is None:
        out = np.empty(returns.shape[1:] + (2,), dtype="float64")

    b = beta_aligned(returns, factor_returns, risk_free, out=out[..., 1])
    alpha_aligned(
        returns,
        factor_returns,
        risk_free,
        period,
        annualization,
        out=out[..., 0],
        _beta=b,
    )

    return out


roll_alpha_beta_aligned = _create_binary_vectorized_roll_function(
    alpha_beta_aligned,
)


def alpha(
    returns,
    factor_returns,
    risk_free=0.0,
    period=DAILY,
    annualization=None,
    out=None,
    _beta=None,
):
    """Calculates annualized alpha.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns : pd.Series
        Daily noncumulative returns of the factor to which beta is
        computed. Usually a benchmark such as the market.
        - This is in the same style as returns.
    risk_free : int, float, optional
        Constant risk-free return throughout the period. For example, the
        interest rate on a three month us treasury bill.
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    annualization : int, optional
        Used to suppress default values available in `period` to convert
        returns into annual returns. Value should be the annual frequency of
        `returns`.
        - See full explanation in :func:`~empyrical.stats.annual_return`.
    _beta : float, optional
        The beta for the given inputs, if already known. Will be calculated
        internally if not provided.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.

    Returns:
    -------
    float
        Alpha.
    """
    if not (isinstance(returns, np.ndarray) and isinstance(factor_returns, np.ndarray)):
        returns, factor_returns = _aligned_series(returns, factor_returns)

    return alpha_aligned(
        returns,
        factor_returns,
        risk_free=risk_free,
        period=period,
        annualization=annualization,
        out=out,
        _beta=_beta,
    )


roll_alpha = _create_binary_vectorized_roll_function(alpha)


def alpha_aligned(
    returns,
    factor_returns,
    risk_free=0.0,
    period=DAILY,
    annualization=None,
    out=None,
    _beta=None,
):
    """Calculates annualized alpha.

    If they are pd.Series, expects returns and factor_returns have already
    been aligned on their labels.  If np.ndarray, these arguments should have
    the same shape.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns : pd.Series or np.ndarray
        Daily noncumulative returns of the factor to which beta is
        computed. Usually a benchmark such as the market.
        - This is in the same style as returns.
    risk_free : int, float, optional
        Constant risk-free return throughout the period. For example, the
        interest rate on a three month us treasury bill.
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    annualization : int, optional
        Used to suppress default values available in `period` to convert
        returns into annual returns. Value should be the annual frequency of
        `returns`.
        - See full explanation in :func:`~empyrical.stats.annual_return`.
    _beta : float, optional
        The beta for the given inputs, if already known. Will be calculated
        internally if not provided.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.

    Returns:
    -------
    alpha : float
    """
    allocated_output = out is None
    if allocated_output:
        out = np.empty(returns.shape[1:], dtype="float64")

    if len(returns) < 2:
        out[()] = np.nan
        if returns.ndim == 1:
            out = out.item()
        return out

    ann_factor = annualization_factor(period, annualization)

    if _beta is None:
        _beta = beta_aligned(returns, factor_returns, risk_free)

    adj_returns = _adjust_returns(returns, risk_free)
    adj_factor_returns = _adjust_returns(factor_returns, risk_free)
    alpha_series = adj_returns - (_beta * adj_factor_returns)

    out = np.subtract(
        np.power(
            np.add(nanmean(alpha_series, axis=0, out=out), 1, out=out),
            ann_factor,
            out=out,
        ),
        1,
        out=out,
    )

    if allocated_output and isinstance(returns, pd.DataFrame):
        out = pd.Series(out)

    if returns.ndim == 1:
        out = out.item()

    return out


roll_alpha_aligned = _create_binary_vectorized_roll_function(alpha_aligned)


def beta(returns, factor_returns, risk_free=0.0, out=None):
    """Calculates beta.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns : pd.Series
         Daily noncumulative returns of the factor to which beta is
         computed. Usually a benchmark such as the market.
         - This is in the same style as returns.
    risk_free : int, float, optional
        Constant risk-free return throughout the period. For example, the
        interest rate on a three month us treasury bill.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.

    Returns:
    -------
    beta : float
    """
    if not (isinstance(returns, np.ndarray) and isinstance(factor_returns, np.ndarray)):
        returns, factor_returns = _aligned_series(returns, factor_returns)

    return beta_aligned(
        returns,
        factor_returns,
        risk_free=risk_free,
        out=out,
    )


roll_beta = _create_binary_vectorized_roll_function(beta)


def beta_aligned(returns, factor_returns, risk_free=0.0, out=None):
    """Calculates beta.

    If they are pd.Series, expects returns and factor_returns have already
    been aligned on their labels.  If np.ndarray, these arguments should have
    the same shape.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns : pd.Series or np.ndarray
         Daily noncumulative returns of the factor to which beta is
         computed. Usually a benchmark such as the market.
         - This is in the same style as returns.
    risk_free : int, float, optional
        Constant risk-free return throughout the period. For example, the
        interest rate on a three month us treasury bill.
    out : array-like, optional
        Array to use as output buffer.
        If not passed, a new array will be created.

    Returns:
    -------
    beta : float
        Beta.
    """
    # Cache these as locals since we're going to call them multiple times.
    nan = np.nan
    isnan = np.isnan

    returns_1d = returns.ndim == 1
    if returns_1d:
        returns = np.asanyarray(returns)[:, np.newaxis]

    if factor_returns.ndim == 1:
        factor_returns = np.asanyarray(factor_returns)[:, np.newaxis]

    _, M = returns.shape

    if out is None:
        out = np.full(M, nan)
    elif out.ndim == 0:
        out = out[np.newaxis]

    if len(returns) < 1 or len(factor_returns) < 2:
        out[()] = nan
        if returns_1d:
            out = out.item()
        return out
    
    independent = np.where(
        isnan(returns),
        nan,
        factor_returns,
    )

    ind_residual = independent - nanmean(independent, axis=0)

    covariances = nanmean(ind_residual * returns, axis=0)

    np.square(ind_residual, out=ind_residual)
    independent_variances = nanmean(ind_residual, axis=0)
    independent_variances[independent_variances < 1.0e-30] = np.nan

    np.divide(covariances, independent_variances, out=out)

    if returns_1d:
        out = out.item()

    return out


roll_beta_aligned = _create_binary_vectorized_roll_function(beta_aligned)


def stability_of_timeseries(returns):
    """Determines R-squared of a linear fit to the cumulative log returns.
    
    Computes an ordinary least squares linear fit, and returns R-squared.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.

    Returns:
    -------
    float
        R-squared.

    """
    if len(returns) < 2:
        return np.nan

    returns = np.asanyarray(returns)
    returns = returns[~np.isnan(returns)]

    cum_log_returns = np.log1p(returns).cumsum()
    rhat = stats.linregress(np.arange(len(cum_log_returns)), cum_log_returns)[2]

    return rhat**2


def tail_ratio(returns):
    """Determines the ratio between the right (95%) and left tail (5%).

    For example, a ratio of 0.25 means that losses are four times
    as bad as profits.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
         - See full explanation in :func:`~empyrical.stats.cum_returns`.

    Returns:
    -------
    tail_ratio : float
    """
    if len(returns) < 1:
        return np.nan

    returns = np.asanyarray(returns)
    # Be tolerant of nan's
    returns = returns[~np.isnan(returns)]
    if len(returns) < 1:
        return np.nan

    return np.abs(np.percentile(returns, 95)) / np.abs(np.percentile(returns, 5))


def capture(returns, factor_returns, period=DAILY):
    """Compute capture ratio.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns : pd.Series or np.ndarray
        Noncumulative returns of the factor to which beta is
        computed. Usually a benchmark such as the market.
        - This is in the same style as returns.
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    Returns:
    -------
    capture_ratio : float

    Note:
    ----
    See http://www.investopedia.com/terms/u/up-market-capture-ratio.asp for
    details.
    """
    return annual_return(returns, period=period) / annual_return(factor_returns, period=period)


def beta_fragility_heuristic(returns, factor_returns):
    """Estimate fragility to drops in beta.

        Parameters
        ----------
        returns : pd.Series or np.ndarray
            Daily returns of the strategy, noncumulative.
            - See full explanation in :func:`~empyrical.stats.cum_returns`.
        factor_returns : pd.Series or np.ndarray
             Daily noncumulative returns of the factor to which beta is
             computed. Usually a benchmark such as the market.
             - This is in the same style as returns.

    Returns:
        -------
        float, np.nan
            The beta fragility of the strategy.

    Note:
        ----
        A negative return value indicates potential losses
        could follow volatility in beta.
        The magnitude of the negative value indicates the size of
        the potential loss.
        seealso::
        `A New Heuristic Measure of Fragility and
    Tail Risks: Application to Stress Testing`
            https://www.imf.org/external/pubs/ft/wp/2012/wp12216.pdf
            An IMF Working Paper describing the heuristic
    """
    if len(returns) < 3 or len(factor_returns) < 3:
        return np.nan

    return beta_fragility_heuristic_aligned(*_aligned_series(returns, factor_returns))


def beta_fragility_heuristic_aligned(returns, factor_returns):
    """Estimate fragility to drops in beta.

        Parameters
        ----------
        returns : pd.Series or np.ndarray
            Daily returns of the strategy, noncumulative.
            - See full explanation in :func:`~empyrical.stats.cum_returns`.
        factor_returns : pd.Series or np.ndarray
             Daily noncumulative returns of the factor to which beta is
             computed. Usually a benchmark such as the market.
             - This is in the same style as returns.

    Returns:
        -------
        float, np.nan
            The beta fragility of the strategy.

    Note:
        ----
        If they are pd.Series, expects returns and factor_returns have already
        been aligned on their labels.  If np.ndarray, these arguments should
        have the same shape.
        seealso::
        `A New Heuristic Measure of Fragility and
    Tail Risks: Application to Stress Testing`
            https://www.imf.org/external/pubs/ft/wp/2012/wp12216.pdf
            An IMF Working Paper describing the heuristic
    """
    if len(returns) < 3 or len(factor_returns) < 3:
        return np.nan

    # combine returns and factor returns into pairs
    returns_series = pd.Series(returns)
    factor_returns_series = pd.Series(factor_returns)
    pairs = pd.concat([returns_series, factor_returns_series], axis=1)
    pairs.columns = ["returns", "factor_returns"]

    # exclude any rows where returns are nan
    pairs = pairs.dropna()
    # sort by beta
    pairs = pairs.sort_values(by="factor_returns")

    # find the three vectors, using median of 3
    start_index = 0
    mid_index = int(np.around(len(pairs) / 2, 0))
    end_index = len(pairs) - 1

    (start_returns, start_factor_returns) = pairs.iloc[start_index]
    (mid_returns, mid_factor_returns) = pairs.iloc[mid_index]
    (end_returns, end_factor_returns) = pairs.iloc[end_index]

    factor_returns_range = end_factor_returns - start_factor_returns
    start_returns_weight = 0.5
    end_returns_weight = 0.5

    # find weights for the start and end returns
    # using a convex combination
    if factor_returns_range != 0:
        start_returns_weight = (mid_factor_returns - start_factor_returns) / factor_returns_range
        end_returns_weight = (end_factor_returns - mid_factor_returns) / factor_returns_range

    # calculate fragility heuristic
    heuristic = (start_returns_weight * start_returns) + (end_returns_weight * end_returns) - mid_returns

    return heuristic


def gpd_risk_estimates(returns, var_p=0.01):
    """Estimate VaR and ES using the Generalized Pareto Distribution (GPD).

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    var_p : float
        The percentile to use for estimating the VaR and ES

    Returns:
    -------
    [threshold, scale_param, shape_param, var_estimate, es_estimate]
        : list[float]
        threshold - the threshold use to cut off exception tail losses
        scale_param - a parameter (often denoted by sigma, capturing the
            scale, related to variance)
        shape_param - a parameter (often denoted by xi, capturing the shape
         or type of the distribution)
        var_estimate - an estimate for the VaR for the given percentile
        es_estimate - an estimate for the ES for the given percentile

    Note:
    ----
    see also::
    `An Application of Extreme Value Theory for Measuring Risk
    <https://link.springer.com/article/10.1007/s10614-006-9025-7>`
        A paper describing how to use the Generalized Pareto
        Distribution to estimate VaR and ES.
    """
    if len(returns) < 3:
        result = np.zeros(5)
        if isinstance(returns, pd.Series):
            result = pd.Series(result)
        return result
    return gpd_risk_estimates_aligned(*_aligned_series(returns, var_p))


def gpd_risk_estimates_aligned(returns, var_p=0.01):
    """Estimate VaR and ES using the Generalized Pareto Distribution (GPD).

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    var_p : float
        The percentile to use for estimating the VaR and ES

    Returns:
    -------
    [threshold, scale_param, shape_param, var_estimate, es_estimate]
        : list[float]
        threshold - the threshold use to cut off exception tail losses
        scale_param - a parameter (often denoted by sigma, capturing the
            scale, related to variance)
        shape_param - a parameter (often denoted by xi, capturing the shape
        or type of the distribution)
        var_estimate - an estimate for the VaR for the given percentile
        es_estimate - an estimate for the ES for the given percentile

    Note:
    ----
    seealso::
    `An Application of Extreme Value Theory for Measuring Risk
    <https://link.springer.com/article/10.1007/s10614-006-9025-7>`
        A paper describing how to use the Generalized Pareto
        Distribution to estimate VaR and ES.
    """
    result = np.zeros(5)
    if not len(returns) < 3:
        DEFAULT_THRESHOLD = 0.2
        MINIMUM_THRESHOLD = 0.000000001

        try:
            returns_array = pd.Series(returns).to_numpy()
        except AttributeError:
            # while zipline requires support for pandas < 0.25
            returns_array = pd.Series(returns).as_matrix()

        flipped_returns = -1 * returns_array
        losses = flipped_returns[flipped_returns > 0]
        threshold = DEFAULT_THRESHOLD
        finished = False
        scale_param = 0
        shape_param = 0
        while not finished and threshold > MINIMUM_THRESHOLD:
            losses_beyond_threshold = losses[losses >= threshold]
            param_result = _gpd_loglikelihood_minimizer_aligned(losses_beyond_threshold)
            if param_result[0] is not False and param_result[1] is not False:
                scale_param = param_result[0]
                shape_param = param_result[1]
                var_estimate = _gpd_var_calculator(
                    threshold,
                    scale_param,
                    shape_param,
                    var_p,
                    len(losses),
                    len(losses_beyond_threshold),
                )
                # non-negative shape parameter is required for fat tails
                # non-negative VaR estimate is required for loss of some kind
                if shape_param > 0 and var_estimate > 0:
                    finished = True
            if not finished:
                threshold = threshold / 2
        if finished:
            es_estimate = _gpd_es_calculator(var_estimate, threshold, scale_param, shape_param)
            result = np.array(
                [
                    threshold,
                    scale_param,
                    shape_param,
                    var_estimate,
                    es_estimate,
                ]
            )
    if isinstance(returns, pd.Series):
        result = pd.Series(result)
    return result


def _gpd_es_calculator(var_estimate, threshold, scale_param, shape_param):
    result = 0
    if (1 - shape_param) != 0:
        # this formula is from Gilli and Kellezi pg. 8
        var_ratio = var_estimate / (1 - shape_param)
        param_ratio = (scale_param - (shape_param * threshold)) / (1 - shape_param)
        result = var_ratio + param_ratio
    return result


def _gpd_var_calculator(threshold, scale_param, shape_param, probability, total_n, exceedance_n):
    result = 0
    if exceedance_n > 0 and shape_param > 0:
        # this formula is from Gilli and Kellezi pg. 12
        param_ratio = scale_param / shape_param
        prob_ratio = (total_n / exceedance_n) * probability
        result = threshold + (param_ratio * (pow(prob_ratio, -shape_param) - 1))
    return result


def _gpd_loglikelihood_minimizer_aligned(price_data):
    result = [False, False]
    DEFAULT_SCALE_PARAM = 1
    DEFAULT_SHAPE_PARAM = 1
    if len(price_data) > 0:
        gpd_loglikelihood_lambda = _gpd_loglikelihood_factory(price_data)
        optimization_results = optimize.minimize(
            gpd_loglikelihood_lambda,
            np.array([DEFAULT_SCALE_PARAM, DEFAULT_SHAPE_PARAM]),
            method="Nelder-Mead",
        )
        if optimization_results.success:
            resulting_params = optimization_results.x
            if len(resulting_params) == 2:
                result[0] = resulting_params[0]
                result[1] = resulting_params[1]
    return result


def _gpd_loglikelihood_factory(price_data):
    return lambda params: _gpd_loglikelihood(params, price_data)


def _gpd_loglikelihood(params, price_data):
    if params[1] != 0:
        return -_gpd_loglikelihood_scale_and_shape(params[0], params[1], price_data)
    return -_gpd_loglikelihood_scale_only(params[0], price_data)


def _gpd_loglikelihood_scale_and_shape(scale, shape, price_data):
    n = len(price_data)
    result = -1 * float_info.max
    if scale != 0:
        param_factor = shape / scale
        if shape != 0 and param_factor >= 0 and scale >= 0:
            result = (-n * np.log(scale)) - (((1 / shape) + 1) * (np.log((shape / scale * price_data) + 1)).sum())
    return result


def _gpd_loglikelihood_scale_only(scale, price_data):
    n = len(price_data)
    data_sum = price_data.sum()
    result = -1 * float_info.max
    if scale >= 0:
        result = (-n * np.log(scale)) - (data_sum / scale)
    return result


def up_capture(returns, factor_returns, **kwargs):
    """Compute the capture ratio for periods when the benchmark return is positive.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns : pd.Series or np.ndarray
        Noncumulative returns of the factor to which beta is
        computed. Usually a benchmark such as the market.
        - This is in the same style as returns.
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    Returns:
    -------
    up_capture : float

    Note:
    ----
    See http://www.investopedia.com/terms/u/up-market-capture-ratio.asp for
    more information.
    """
    return up(returns, factor_returns, function=capture, **kwargs)


def down_capture(returns, factor_returns, **kwargs):
    """Compute the capture ratio for periods when the benchmark return is negative.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns : pd.Series or np.ndarray
        Noncumulative returns of the factor to which beta is
        computed. Usually a benchmark such as the market.
        - This is in the same style as returns.
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    Returns:
    -------
    down_capture : float

    Note:
    ----
    See http://www.investopedia.com/terms/d/down-market-capture-ratio.asp for
    more information.
    """
    return down(returns, factor_returns, function=capture, **kwargs)


def up_down_capture(returns, factor_returns, **kwargs):
    """Computes the ratio of up_capture to down_capture.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns : pd.Series or np.ndarray
        Noncumulative returns of the factor to which beta is
        computed. Usually a benchmark such as the market.
        - This is in the same style as returns.
    period : str, optional
        Defines the periodicity of the 'returns' data for purposes of
        annualizing. Value ignored if `annualization` parameter is specified.
        Defaults are::

            'monthly':12
            'weekly': 52
            'daily': 252

    Returns:
    -------
    up_down_capture : float
        the updown capture ratio
    """
    return up_capture(returns, factor_returns, **kwargs) / down_capture(returns, factor_returns, **kwargs)


def batting_average(returns, factor_returns):
    """Computes the batting average.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns : pd.Series or np.ndarray
        Noncumulative returns of the factor to which beta is
        computed. Usually a benchmark such as the market.
        - This is in the same style as returns.

    Returns:
    -------
    batting_average : pd.Series
        batting average, up market, down market

    Note:
    ----
    See https://www.investopedia.com/terms/b/batting-average.asp for
    more information.
    """
    results = OrderedDict(
        {
            "batting average": np.nan,
            "up market": np.nan,
            "down market": np.nan,
        }
    )
    active_return = _adjust_returns(returns, factor_returns)
    bt = active_return > 0
    up_value = active_return[factor_returns >= 0.0] > 0
    down_value = active_return[factor_returns < 0.0] > 0
    if len(bt) > 0:
        results["batting average"] = bt.mean()
    if len(up_value) > 0:
        results["up market"] = up_value.mean()
    if len(down_value) > 0:
        results["down market"] = down_value.mean()

    return pd.Series(results, index=results.keys())


def up_alpha_beta(returns, factor_returns, **kwargs):
    """Computes alpha and beta for periods when the benchmark return is positive.

    Parameters
    ----------
    see documentation for `alpha_beta`.

    Returns:
    -------
    float
        Alpha.
    float
        Beta.
    """
    return up(returns, factor_returns, function=alpha_beta_aligned, **kwargs)


def down_alpha_beta(returns, factor_returns, **kwargs):
    """Computes alpha and beta for periods when the benchmark return is negative.

    Parameters
    ----------
    see documentation for `alpha_beta`.

    Returns:
    -------
    alpha : float
    beta : float
    """
    return down(returns, factor_returns, function=alpha_beta_aligned, **kwargs)


def roll_up_capture(returns, factor_returns, window=10, **kwargs):
    """Computes the up capture measure over a rolling window.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.

    factor_returns : pd.Series or np.ndarray
        Noncumulative returns of the factor to which beta is
        computed. Usually a benchmark such as the market.
        - This is in the same style as returns.

    window : int, required
        Size of the rolling window in terms of the periodicity of the data.
        - eg window = 60, periodicity=DAILY, represents a rolling 60 day window
    """
    return roll(returns, factor_returns, window=window, function=up_capture, **kwargs)


def roll_down_capture(returns, factor_returns, window=10, **kwargs):
    """Computes the down capture measure over a rolling window.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.

    factor_returns : pd.Series or np.ndarray
        Noncumulative returns of the factor to which beta is
        computed. Usually a benchmark such as the market.
        - This is in the same style as returns.

    window : int, required
        Size of the rolling window in terms of the periodicity of the data.
        - eg window = 60, periodicity=DAILY, represents a rolling 60 day window
    """
    return roll(returns, factor_returns, window=window, function=down_capture, **kwargs)


def roll_up_down_capture(returns, factor_returns, window=10, **kwargs):
    """Computes the up/down capture measure over a rolling window.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.

    factor_returns : pd.Series or np.ndarray
        Noncumulative returns of the factor to which beta is
        computed. Usually a benchmark such as the market.
        - This is in the same style as returns.

    window : int, required
        Size of the rolling window in terms of the periodicity of the data.
        - eg window = 60, periodicity=DAILY, represents a rolling 60 day window
    """
    return roll(
        returns,
        factor_returns,
        window=window,
        function=up_down_capture,
        **kwargs,
    )


def value_at_risk(returns, cutoff=0.05):
    """Value at risk (VaR) of a returns stream.

    Parameters
    ----------
    returns : pandas.Series or 1-D numpy.array
        Non-cumulative daily returns.
    cutoff : float, optional
        Decimal representing the percentage cutoff for the bottom percentile of
        returns. Defaults to 0.05.

    Returns:
    -------
    VaR : float
        The VaR value.
    """
    return np.percentile(returns, 100 * cutoff)


def conditional_value_at_risk(returns, cutoff=0.05):
    """Conditional value at risk (CVaR) of a returns stream.

    CVaR measures the expected single-day returns of an asset on that asset's
    worst performing days, where "worst-performing" is defined as falling below
    ``cutoff`` as a percentile of all daily returns.

    Parameters
    ----------
    returns : pandas.Series or 1-D numpy.array
        Non-cumulative daily returns.
    cutoff : float, optional
        Decimal representing the percentage cutoff for the bottom percentile of
        returns. Defaults to 0.05.

    Returns:
    -------
    CVaR : float
        The CVaR value.
    """
    # PERF: Instead of using the 'value_at_risk' function to find the cutoff
    # value, which requires a call to numpy.percentile, determine the cutoff
    # index manually and partition out the lowest returns values. The value at
    # the cutoff index should be included in the partition.
    cutoff_index = int((len(returns) - 1) * cutoff)
    return np.mean(np.partition(returns, cutoff_index)[: cutoff_index + 1])


def rolling_beta(returns, factor_returns, rolling_window=APPROX_BDAYS_PER_MONTH * 6):
    """Determines the rolling beta of a strategy.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
         - See full explanation in tears.create_full_tear_sheet.
    factor_returns : pd.Series or pd.DataFrame
        Daily noncumulative returns of the benchmark factor to which betas are
        computed. Usually a benchmark such as market returns.
         - If DataFrame is passed, computes rolling beta for each column.
         - This is in the same style as returns.
    rolling_window : int, optional
        The size of the rolling window, in days, over which to compute
        beta (default 6 months).

    Returns:
    -------
    pd.Series
        Rolling beta.

    Note:
    -----
    See https://en.wikipedia.org/wiki/Beta_(finance) for more details.
    """
    if factor_returns.ndim > 1:
        return factor_returns.apply(partial(rolling_beta, returns), rolling_window=rolling_window)
    out = pd.Series(index=returns.index, dtype="float64")
    for beg, end in zip(returns.index[0:-rolling_window], returns.index[rolling_window:], strict=False):
        out.loc[end] = beta(returns.loc[beg:end], factor_returns.loc[beg:end])
    return out


def gross_lev(positions):
    """Calculates the gross leverage of a strategy.

    Parameters
    ----------
    positions : pd.DataFrame
        Daily net position values.
         - See full explanation in tears.create_full_tear_sheet.

    Returns:
    -------
    pd.Series
        Gross leverage.
    """
    exposure = positions.drop("cash", axis=1).abs().sum(axis=1)
    return exposure / positions.sum(axis=1)
