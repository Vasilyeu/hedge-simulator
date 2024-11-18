"""Plotting module
"""

import pandas as pd
import plotly.express as px

from src.performance.portfolio import Portfolio


def plot_cumulative_returns(portfolio: Portfolio, benchmark: Portfolio, hedge_portfolio: Portfolio | None = None):
    """Plot cumulative returns
    :param portfolio: analyzed Portfolio
    :param benchmark: benchmark Portfolio
    :param hedge_portfolio: hedged Portfolio
    :return: plotly plot
    """
    benchmark_ticker = benchmark.transactions["ticker"][0]
    data = pd.DataFrame(
        {
            "portfolio": portfolio.cumulative_return,
            benchmark_ticker: benchmark.cumulative_return,
        }
    )
    if hedge_portfolio is not None:
        data["portfolio_hedged"] = hedge_portfolio.cumulative_return
    fig = px.line(data, y=list(data.columns), title="Cumulative Returns")
    return fig
