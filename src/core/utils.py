"""Utility functions for stats module."""
from functools import wraps

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import as_strided

try:
    # fast versions
    import bottleneck as bn

    def _wrap_function(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            out = kwargs.pop("out", None)
            data = f(*args, **kwargs)
            if out is None:
                out = data
            else:
                out[()] = data

            return out

        return wrapped

    nanmean = _wrap_function(bn.nanmean)
    nanstd = _wrap_function(bn.nanstd)
    nansum = _wrap_function(bn.nansum)
    nanmax = _wrap_function(bn.nanmax)
    nanmin = _wrap_function(bn.nanmin)
    nanargmax = _wrap_function(bn.nanargmax)
    nanargmin = _wrap_function(bn.nanargmin)
except ImportError:
    # slower numpy
    nanmean = np.nanmean
    nanstd = np.nanstd
    nansum = np.nansum
    nanmax = np.nanmax
    nanmin = np.nanmin
    nanargmax = np.nanargmax
    nanargmin = np.nanargmin


def roll(*args, **kwargs):
    """Calculates a given statistic across a rolling time period.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns (optional): float / series
        Benchmark return to compare returns against.
    function:
        the function to run for each rolling window.
    window (keyword): int
        the number of periods included in each calculation.
    (other keywords): other keywords that are required to be passed to the
        function in the 'function' argument may also be passed in.

    Returns:
    -------
    np.ndarray, pd.Series
        depends on input type
        ndarray(s) ==> ndarray
        Series(s) ==> pd.Series

        A Series or ndarray of the results of the stat across the rolling
        window.

    """
    func = kwargs.pop("function")
    window = kwargs.pop("window")
    if len(args) > 2:
        raise ValueError("Cannot pass more than 2 return sets")

    if len(args) == 2 and not isinstance(args[0], type(args[1])):
            raise ValueError("The two returns arguments are not the same.")

    if isinstance(args[0], np.ndarray):
        return _roll_ndarray(func, window, *args, **kwargs)
    return _roll_pandas(func, window, *args, **kwargs)


def up(returns, factor_returns, **kwargs):
    """Calculates a given statistic filtering only positive factor return periods.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns (optional): float / series
        Benchmark return to compare returns against.
    function:
        the function to run for each rolling window.
    (other keywords): other keywords that are required to be passed to the
        function in the 'function' argument may also be passed in.

    Returns:
    -------
    Same as the return of the function
    """
    func = kwargs.pop("function")
    returns = returns[factor_returns > 0]
    factor_returns = factor_returns[factor_returns > 0]
    return func(returns, factor_returns, **kwargs)


def down(returns, factor_returns, **kwargs):
    """Calculates a given statistic filtering only negative factor return periods.

    Parameters
    ----------
    returns : pd.Series or np.ndarray
        Daily returns of the strategy, noncumulative.
        - See full explanation in :func:`~empyrical.stats.cum_returns`.
    factor_returns (optional): float / series
        Benchmark return to compare returns against.
    function:
        the function to run for each rolling window.
    (other keywords): other keywords that are required to be passed to the
        function in the 'function' argument may also be passed in.

    Returns:
    -------
    Same as the return of the 'function'
    """
    func = kwargs.pop("function")
    returns = returns[factor_returns < 0]
    factor_returns = factor_returns[factor_returns < 0]
    return func(returns, factor_returns, **kwargs)


def _roll_ndarray(func, window, *args, **kwargs):
    data = []
    for i in range(window, len(args[0]) + 1):
        rets = [s[i - window: i] for s in args]
        data.append(func(*rets, **kwargs))
    return np.array(data)


def _roll_pandas(func, window, *args, **kwargs):
    data = {}
    index_values = []
    for i in range(window, len(args[0]) + 1):
        rets = [s.iloc[i - window: i] for s in args]
        index_value = args[0].index[i - 1]
        index_values.append(index_value)
        data[index_value] = func(*rets, **kwargs)
    return pd.Series(
        data,
        index=type(args[0].index)(index_values),
        dtype=np.float64,
    )


def rolling_window(array, length, mutable=False):
    """Restride an array of shape.

        (X_0, ... X_N)

    into an array of shape

        (length, X_0 - length + 1, ... X_N)

    where each slice at index i along the first axis is equivalent to

        result[i] = array[length * i:length * (i + 1)]

    Parameters
    ----------
    array : np.ndarray
        The base array.
    length : int
        Length of the synthetic first axis to generate.
    mutable : bool, optional
        Return a mutable array? The returned array shares the same memory as
        the input array. This means that writes into the returned array affect
        ``array``. The returned array also uses strides to map the same values
        to multiple indices. Writes to a single index may appear to change many
        values in the returned array.

    Returns:
    -------
    out : np.ndarray

    Example:
    -------
    >>> from numpy import arange
    >>> a = arange(25).reshape(5, 5)
    >>> a
    array([[ 0,  1,  2,  3,  4],
           [ 5,  6,  7,  8,  9],
           [10, 11, 12, 13, 14],
           [15, 16, 17, 18, 19],
           [20, 21, 22, 23, 24]])

    >>> rolling_window(a, 2)
    array([[[ 0,  1,  2,  3,  4],
            [ 5,  6,  7,  8,  9]],
    <BLANKLINE>
           [[ 5,  6,  7,  8,  9],
            [10, 11, 12, 13, 14]],
    <BLANKLINE>
           [[10, 11, 12, 13, 14],
            [15, 16, 17, 18, 19]],
    <BLANKLINE>
           [[15, 16, 17, 18, 19],
            [20, 21, 22, 23, 24]]])
    """
    if not length:
        raise ValueError("Can't have 0-length window")

    orig_shape = array.shape
    if not orig_shape:
        raise IndexError("Can't restride a scalar.")
    elif orig_shape[0] < length:
        raise IndexError(
            f"Can't restride array of shape {
                orig_shape} with" f" a window length of {length}"
        )

    num_windows = orig_shape[0] - length + 1
    new_shape = (num_windows, length) + orig_shape[1:]

    new_strides = (array.strides[0],) + array.strides

    out = as_strided(array, new_shape, new_strides)
    out.setflags(write=mutable)
    return out


def _create_unary_vectorized_roll_function(function):
    def unary_vectorized_roll(arr, window, out=None, **kwargs):
        """Computes the {human_readable} measure over a rolling window.

        Parameters
        ----------
        arr : array-like
            The array to compute the rolling {human_readable} over.
        window : int
            Size of the rolling window in terms of the periodicity of the data.
        out : array-like, optional
            Array to use as output buffer.
            If not passed, a new array will be created.
        **kwargs
            Forwarded to :func:`~empyrical.{name}`.

        Returns:
        -------
        rolling_{name} : array-like
            The rolling {human_readable}.
        """
        allocated_output = out is None

        if len(arr):
            out = function(
                rolling_window(_flatten(arr), min(len(arr), window)).T,
                out=out,
                **kwargs,
            )
        else:
            out = np.empty(0, dtype="float64")

        if allocated_output and isinstance(arr, pd.Series):
            out = pd.Series(out, index=arr.index[-len(out):])

        return out

    unary_vectorized_roll.__doc__ = unary_vectorized_roll.__doc__.format(
        name=function.__name__,
        human_readable=function.__name__.replace("_", " "),
    )
    unary_vectorized_roll.__name__ = f"rolling_{function.__name__}"

    return unary_vectorized_roll


def _create_binary_vectorized_roll_function(function):
    def binary_vectorized_roll(lhs, rhs, window, out=None, **kwargs):
        """Computes the {human_readable} measure over a rolling window.

        Parameters
        ----------
        lhs : array-like
            The first array to pass to the rolling {human_readable}.
        rhs : array-like
            The second array to pass to the rolling {human_readable}.
        window : int
            Size of the rolling window in terms of the periodicity of the data.
        out : array-like, optional
            Array to use as output buffer.
            If not passed, a new array will be created.
        **kwargs
            Forwarded to :func:`~empyrical.{name}`.

        Returns:
        -------
        rolling_{name} : array-like
            The rolling {human_readable}.
        """
        allocated_output = out is None

        if window >= 1 and len(lhs) and len(rhs):
            out = function(
                rolling_window(_flatten(lhs), min(len(lhs), window)).T,
                rolling_window(_flatten(rhs), min(len(rhs), window)).T,
                out=out,
                **kwargs,
            )
        elif allocated_output:
            out = np.empty(0, dtype="float64")
        else:
            out[()] = np.nan

        if allocated_output:
            if out.ndim == 1 and isinstance(lhs, pd.Series):
                out = pd.Series(out, index=lhs.index[-len(out):])
            elif out.ndim == 2 and isinstance(lhs, pd.Series):
                out = pd.DataFrame(out, index=lhs.index[-len(out):])
        return out

    binary_vectorized_roll.__doc__ = binary_vectorized_roll.__doc__.format(
        name=function.__name__,
        human_readable=function.__name__.replace("_", " "),
    )

    binary_vectorized_roll.__name__ = f"rolling_{function.__name__}"

    return binary_vectorized_roll


def _flatten(arr):
    return arr if not isinstance(arr, pd.Series) else arr.values


def _aligned_series(*many_series):
    """Aligne series to their indices.
    
    Return a new list of series containing the data in the input series, but
    with their indices aligned. NaNs will be filled in for missing values.

    Parameters
    ----------
    *many_series
        The series to align.

    Returns:
    -------
    aligned_series : iterable[array-like]
        A new list of series containing the data in the input series, but
        with their indices aligned. NaNs will be filled in for missing values.

    """
    head = many_series[0]
    tail = many_series[1:]
    n = len(head)
    if isinstance(head, np.ndarray) and all(len(s) == n and isinstance(s, np.ndarray) for s in tail):
        # optimization: ndarrays of the same length are already aligned
        return many_series

    # dataframe has no ``itervalues``
    return (v for _, v in pd.concat(map(_to_pandas, many_series), axis=1).items())


def _to_pandas(ob):
    """Convert an array-like to a pandas object.

    Parameters
    ----------
    ob : array-like
        The object to convert.

    Returns:
    -------
    pandas_structure : pd.Series or pd.DataFrame
        The correct structure based on the dimensionality of the data.
    """
    if isinstance(ob, pd.Series | pd.DataFrame):
        return ob

    if ob.ndim == 1:
        return pd.Series(ob)
    elif ob.ndim == 2:
        return pd.DataFrame(ob)
    else:
        raise ValueError(
            "cannot convert array of dim > 2 to a pandas structure",
        )


def _adjust_returns(returns, adjustment_factor):
    """Returns the returns series adjusted by adjustment_factor.
    
    Optimizes for the case of adjustment_factor being 0 by returning returns itself, not a copy!

    Parameters
    ----------
    returns : pd.Series or np.ndarray
    adjustment_factor : pd.Series or np.ndarray or float or int

    Returns:
    -------
    adjusted_returns : array-like
    """
    if isinstance(adjustment_factor, float | int) and adjustment_factor == 0:
        return returns
    return returns - adjustment_factor
