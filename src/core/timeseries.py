"""
Timeseries module
"""

from collections import OrderedDict

import numpy as np
import pandas as pd
from scipy import stats

import src.core.stats as ep
from .interesting_periods import PERIODS
from .txn import get_turnover
from .utils import APPROX_BDAYS_PER_YEAR


def value_at_risk(returns, period=None, sigma=2.0):
    """
    Get value at risk (VaR).

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
         - See full explanation in tears.create_full_tear_sheet.
    period : str, optional
        Period over which to calculate VaR. Set to 'weekly',
        'monthly', or 'yearly', otherwise defaults to period of
        returns (typically daily).
    sigma : float, optional
        Standard deviations of VaR, default 2.
    """
    if period is not None:
        returns_agg = ep.aggregate_returns(returns, period)
    else:
        returns_agg = returns.copy()

    return returns_agg.mean() - sigma * returns_agg.std()


SIMPLE_STAT_FUNCS = [
    ep.annual_return,
    ep.cum_returns_final,
    ep.annual_volatility,
    ep.sharpe_ratio,
    ep.calmar_ratio,
    ep.stability_of_timeseries,
    ep.max_drawdown,
    ep.omega_ratio,
    ep.sortino_ratio,
    stats.skew,
    stats.kurtosis,
    ep.tail_ratio,
    value_at_risk,
]

FACTOR_STAT_FUNCS = [
    ep.alpha,
    ep.beta,
]

STAT_FUNC_NAMES = {
    "annual_return": "Annual return",
    "cum_returns_final": "Cumulative returns",
    "annual_volatility": "Annual volatility",
    "sharpe_ratio": "Sharpe ratio",
    "calmar_ratio": "Calmar ratio",
    "stability_of_timeseries": "Stability",
    "max_drawdown": "Max drawdown",
    "omega_ratio": "Omega ratio",
    "sortino_ratio": "Sortino ratio",
    "skew": "Skew",
    "kurtosis": "Kurtosis",
    "tail_ratio": "Tail ratio",
    "common_sense_ratio": "Common sense ratio",
    "value_at_risk": "Daily value at risk",
    "alpha": "Alpha",
    "beta": "Beta",
}


def perf_stats(
    returns,
    factor_returns=None,
    positions=None,
    transactions=None,
    turnover_denom="AGB",
):
    """
    Calculates various performance metrics of a strategy, for use in
    plotting.show_perf_stats.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
         - See full explanation in tears.create_full_tear_sheet.
    factor_returns : pd.Series, optional
        Daily noncumulative returns of the benchmark factor to which betas are
        computed. Usually a benchmark such as market returns.
         - This is in the same style as returns.
         - If None, do not compute alpha, beta, and information ratio.
    positions : pd.DataFrame
        Daily net position values.
         - See full explanation in tears.create_full_tear_sheet.
    transactions : pd.DataFrame
        Prices and amounts of executed trades. One row per trade.
        - See full explanation in tears.create_full_tear_sheet.
    turnover_denom : str
        Either AGB or portfolio_value, default AGB.
        - See full explanation in txn.get_turnover.

    Returns
    -------
    pd.Series
        Performance metrics.
    """

    statistics = pd.Series(dtype="float64")
    for stat_func in SIMPLE_STAT_FUNCS:
        statistics[STAT_FUNC_NAMES[stat_func.__name__]] = stat_func(returns)

    if not (positions is None or positions.empty):
        statistics["Gross leverage"] = ep.gross_lev(positions).mean()
        if not (transactions is None or transactions.empty):
            statistics["Daily turnover"] = get_turnover(positions, transactions, turnover_denom).mean()
    if factor_returns is not None:
        for stat_func in FACTOR_STAT_FUNCS:
            res = stat_func(returns, factor_returns)
            statistics[STAT_FUNC_NAMES[stat_func.__name__]] = res

    return statistics


def perf_stats_bootstrap(returns, factor_returns=None, return_stats=True):
    """Calculates various bootstrapped performance metrics of a strategy.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
         - See full explanation in tears.create_full_tear_sheet.
    factor_returns : pd.Series, optional
        Daily noncumulative returns of the benchmark factor to which betas are
        computed. Usually a benchmark such as market returns.
         - This is in the same style as returns.
         - If None, do not compute alpha, beta, and information ratio.
    return_stats : boolean (optional)
        If True, returns a DataFrame of mean, median, 5 and 95 percentiles
        for each perf metric.
        If False, returns a DataFrame with the bootstrap samples for
        each perf metric.

    Returns
    -------
    pd.DataFrame
        if return_stats is True:
        - Distributional statistics of bootstrapped sampling
        distribution of performance metrics.
        if return_stats is False:
        - Bootstrap samples for each performance metric.
    """

    bootstrap_values = OrderedDict()

    for stat_func in SIMPLE_STAT_FUNCS:
        stat_name = STAT_FUNC_NAMES[stat_func.__name__]
        bootstrap_values[stat_name] = calc_bootstrap(stat_func, returns)

    if factor_returns is not None:
        for stat_func in FACTOR_STAT_FUNCS:
            stat_name = STAT_FUNC_NAMES[stat_func.__name__]
            bootstrap_values[stat_name] = calc_bootstrap(stat_func, returns, factor_returns=factor_returns)

    bootstrap_values = pd.DataFrame(bootstrap_values)

    if return_stats:
        statistics = bootstrap_values.apply(calc_distribution_stats)
        return statistics.T[["mean", "median", "5%", "95%"]]
    return bootstrap_values


def calc_bootstrap(func, returns, *args, **kwargs):
    """Performs a bootstrap analysis on a user-defined function returning
    a summary statistic.

    Parameters
    ----------
    func : function
        Function that either takes a single array (commonly returns)
        or two arrays (commonly returns and factor returns) and
        returns a single value (commonly a summary
        statistic). Additional args and kwargs are passed as well.
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
         - See full explanation in tears.create_full_tear_sheet.
    factor_returns : pd.Series, optional
        Daily noncumulative returns of the benchmark factor to which betas are
        computed. Usually a benchmark such as market returns.
         - This is in the same style as returns.
    n_samples : int, optional
        Number of bootstrap samples to draw. Default is 1000.
        Increasing this will lead to more stable / accurate estimates.

    Returns
    -------
    numpy.ndarray
        Bootstrapped sampling distribution of passed in func.
    """

    n_samples = kwargs.pop("n_samples", 1000)
    out = np.empty(n_samples)

    factor_returns = kwargs.pop("factor_returns", None)

    for i in range(n_samples):
        idx = np.random.randint(len(returns), size=len(returns))
        returns_i = returns.iloc[idx].reset_index(drop=True)
        if factor_returns is not None:
            factor_returns_i = factor_returns.iloc[idx].reset_index(drop=True)
            out[i] = func(returns_i, factor_returns_i, *args, **kwargs)
        else:
            out[i] = func(returns_i, *args, **kwargs)

    return out


def calc_distribution_stats(x):
    """Calculate various summary statistics of data.

    Parameters
    ----------
    x : numpy.ndarray or pandas.Series
        Array to compute summary statistics for.

    Returns
    -------
    pandas.Series
        Series containing mean, median, std, as well as 5, 25, 75 and
        95 percentiles of passed in values.
    """

    return pd.Series(
        {
            "mean": np.mean(x),
            "median": np.median(x),
            "std": np.std(x),
            "5%": np.percentile(x, 5),
            "25%": np.percentile(x, 25),
            "75%": np.percentile(x, 75),
            "95%": np.percentile(x, 95),
            "IQR": np.subtract.reduce(np.percentile(x, [75, 25])),
        }
    )


def get_max_drawdown_underwater(underwater):
    """
    Determines peak, valley, and recovery dates given an 'underwater'
    DataFrame.

    An underwater DataFrame is a DataFrame that has precomputed
    rolling drawdown.

    Parameters
    ----------
    underwater : pd.Series
       Underwater returns (rolling drawdown) of a strategy.

    Returns
    -------
    peak : datetime
        The maximum drawdown's peak.
    valley : datetime
        The maximum drawdown's valley.
    recovery : datetime
        The maximum drawdown's recovery.
    """

    valley = underwater.idxmin()  # end of the period
    # Find first 0
    peak = underwater[:valley][underwater[:valley] == 0].index[-1]
    # Find last 0
    try:
        recovery = underwater[valley:][underwater[valley:] == 0].index[0]
    except IndexError:
        recovery = np.nan  # drawdown not recovered
    return peak, valley, recovery


def get_top_drawdowns(returns, top=10):
    """
    Finds top drawdowns, sorted by drawdown amount.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
         - See full explanation in tears.create_full_tear_sheet.
    top : int, optional
        The amount of top drawdowns to find (default 10).

    Returns
    -------
    drawdowns : list
        List of drawdown peaks, valleys, and recoveries. See get_max_drawdown.
    """

    returns = returns.copy()
    df_cum = ep.cum_returns(returns, 1.0)
    running_max = np.maximum.accumulate(df_cum)
    underwater = df_cum / running_max - 1

    drawdowns = []
    for _ in range(top):
        peak, valley, recovery = get_max_drawdown_underwater(underwater)
        # Slice out draw-down period
        if not pd.isnull(recovery):
            underwater.drop(underwater[peak:recovery].index[1:-1], inplace=True)
        else:
            # drawdown has not ended yet
            underwater = underwater.loc[:peak]

        drawdowns.append((peak, valley, recovery))
        if (len(returns) == 0) or (len(underwater) == 0) or (np.min(underwater) == 0):
            break

    return drawdowns


def gen_drawdown_table(returns, top=10):
    """
    Places top drawdowns in a table.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
         - See full explanation in tears.create_full_tear_sheet.
    top : int, optional
        The amount of top drawdowns to find (default 10).

    Returns
    -------
    df_drawdowns : pd.DataFrame
        Information about top drawdowns.
    """

    df_cum = ep.cum_returns(returns, 1.0)
    drawdown_periods = get_top_drawdowns(returns, top=top)
    df_drawdowns = pd.DataFrame(
        index=list(range(top)),
        columns=[
            "Net drawdown in %",
            "Peak date",
            "Valley date",
            "Recovery date",
            "Duration",
        ],
    )

    for i, (peak, valley, recovery) in enumerate(drawdown_periods):
        if pd.isnull(recovery):
            df_drawdowns.loc[i, "Duration"] = np.nan
        else:
            df_drawdowns.loc[i, "Duration"] = len(pd.date_range(peak, recovery, freq="B"))
        df_drawdowns.loc[i, "Peak date"] = peak.to_pydatetime().strftime("%Y-%m-%d")
        df_drawdowns.loc[i, "Valley date"] = valley.to_pydatetime().strftime("%Y-%m-%d")
        if isinstance(recovery, float):
            df_drawdowns.loc[i, "Recovery date"] = recovery
        else:
            df_drawdowns.loc[i, "Recovery date"] = recovery.to_pydatetime().strftime("%Y-%m-%d")
        df_drawdowns.loc[i, "Net drawdown in %"] = ((df_cum.loc[peak] - df_cum.loc[valley]) / df_cum.loc[peak]) * 100

    df_drawdowns["Peak date"] = pd.to_datetime(df_drawdowns["Peak date"])
    df_drawdowns["Valley date"] = pd.to_datetime(df_drawdowns["Valley date"])
    df_drawdowns["Recovery date"] = pd.to_datetime(df_drawdowns["Recovery date"])

    return df_drawdowns


def rolling_volatility(returns, rolling_vol_window):
    """
    Determines the rolling volatility of a strategy.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
         - See full explanation in tears.create_full_tear_sheet.
    rolling_vol_window : int
        Length of rolling window, in days, over which to compute.

    Returns
    -------
    pd.Series
        Rolling volatility.
    """

    return returns.rolling(rolling_vol_window).std() * np.sqrt(APPROX_BDAYS_PER_YEAR)


def rolling_sharpe(returns, rolling_sharpe_window):
    """
    Determines the rolling Sharpe ratio of a strategy.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
         - See full explanation in tears.create_full_tear_sheet.
    rolling_sharpe_window : int
        Length of rolling window, in days, over which to compute.

    Returns
    -------
    pd.Series
        Rolling Sharpe ratio.

    Note
    -----
    See https://en.wikipedia.org/wiki/Sharpe_ratio for more details.
    """

    return (
        returns.rolling(rolling_sharpe_window).mean()
        / returns.rolling(rolling_sharpe_window).std()
        * np.sqrt(APPROX_BDAYS_PER_YEAR)
    )


def simulate_paths(is_returns, num_days, num_samples=1000, random_seed=None):
    """
    Gnerate alternate paths using available values from in-sample returns.

    Parameters
    ----------
    is_returns : pandas.core.frame.DataFrame
        Non-cumulative in-sample returns.
    num_days : int
        Number of days to project the probability cone forward.
    num_samples : int
        Number of samples to draw from the in-sample daily returns.
        Each sample will be an array with length num_days.
        A higher number of samples will generate a more accurate
        bootstrap cone.
    random_seed : int
        Seed for the pseudorandom number generator used by the pandas
        sample method.

    Returns
    -------
    samples : numpy.ndarray
    """

    samples = np.empty((num_samples, num_days))
    seed = np.random.RandomState(seed=random_seed)
    for i in range(num_samples):
        samples[i, :] = is_returns.sample(num_days, replace=True, random_state=seed)
    return samples


def summarize_paths(samples, cone_std=(1.0, 1.5, 2.0), starting_value=1.0):
    """
    Gnerate the upper and lower bounds of an n standard deviation
    cone of forecasted cumulative returns.

    Parameters
    ----------
    samples : numpy.ndarray
        Alternative paths, or series of possible outcomes.
    cone_std : list of int/float
        Number of standard devations to use in the boundaries of
        the cone. If multiple values are passed, cone bounds will
        be generated for each value.

    Returns
    -------
    samples : pandas.core.frame.DataFrame
    """

    cum_samples = ep.cum_returns(samples.T, starting_value=starting_value).T

    cum_mean = cum_samples.mean(axis=0)
    cum_std = cum_samples.std(axis=0)

    if isinstance(cone_std, (float, int)):
        cone_std = [cone_std]

    cone_bounds = pd.DataFrame(columns=pd.Index([], dtype="float64"))
    for num_std in cone_std:
        cone_bounds.loc[:, float(num_std)] = cum_mean + cum_std * num_std
        cone_bounds.loc[:, float(-num_std)] = cum_mean - cum_std * num_std

    return cone_bounds


def forecast_cone_bootstrap(
    is_returns,
    num_days,
    cone_std=(1.0, 1.5, 2.0),
    starting_value=1,
    num_samples=1000,
    random_seed=None,
):
    """
    Determines the upper and lower bounds of an n standard deviation
    cone of forecasted cumulative returns. Future cumulative mean and
    standard devation are computed by repeatedly sampling from the
    in-sample daily returns (i.e. bootstrap). This cone is non-parametric,
    meaning it does not assume that returns are normally distributed.

    Parameters
    ----------
    is_returns : pd.Series
        In-sample daily returns of the strategy, noncumulative.
         - See full explanation in tears.create_full_tear_sheet.
    num_days : int
        Number of days to project the probability cone forward.
    cone_std : int, float, or list of int/float
        Number of standard devations to use in the boundaries of
        the cone. If multiple values are passed, cone bounds will
        be generated for each value.
    starting_value : int or float
        Starting value of the out of sample period.
    num_samples : int
        Number of samples to draw from the in-sample daily returns.
        Each sample will be an array with length num_days.
        A higher number of samples will generate a more accurate
        bootstrap cone.
    random_seed : int
        Seed for the pseudorandom number generator used by the pandas
        sample method.

    Returns
    -------
    pd.DataFrame
        Contains upper and lower cone boundaries. Column names are
        strings corresponding to the number of standard devations
        above (positive) or below (negative) the projected mean
        cumulative returns.
    """

    samples = simulate_paths(
        is_returns=is_returns,
        num_days=num_days,
        num_samples=num_samples,
        random_seed=random_seed,
    )

    cone_bounds = summarize_paths(samples=samples, cone_std=cone_std, starting_value=starting_value)

    return cone_bounds


def extract_interesting_date_ranges(returns, periods=None):
    """
    Extracts returns based on interesting events. See
    gen_date_range_interesting.

    Parameters
    ----------
    returns : pd.Series
        Daily returns of the strategy, noncumulative.
         - See full explanation in tears.create_full_tear_sheet.

    Returns
    -------
    ranges : OrderedDict
        Date ranges, with returns, of all valid events.
    """
    if periods is None:
        periods = PERIODS

    returns_dupe = returns.copy()
    returns_dupe.index = returns_dupe.index.map(pd.Timestamp)
    ranges = OrderedDict()
    for name, (start, end) in periods.items():
        try:
            period = returns_dupe.loc[start:end]
            if len(period) == 0:
                continue
            ranges[name] = period
        except BaseException:
            continue

    return ranges
