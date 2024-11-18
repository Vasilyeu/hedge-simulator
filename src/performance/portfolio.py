"""Portfolio and performance
"""

import pandas as pd

from src.data.read import read_prices
from src.performance import metrics


class Portfolio:
    """Class for portfolio data"""

    def __init__(
        self, positions: pd.DataFrame, prices: pd.DataFrame, transactions: pd.DataFrame, start_cash: float | None = None
    ) -> None:
        self.positions = positions
        self.prices = prices
        self.transactions = transactions
        self.start_cash = start_cash
        self._calculate_cash_flow()
        self.capitalisation = self.get_capitalisation()
        self.returns = self.get_returns()
        self.cumulative_return = self._get_cumulative_return()
        self.hedge_cost = 0
        self.cash = 0

    def performance(self, baseline=None, start_date: str | None = None) -> dict:
        """Calculate performance of portfolio
        :param baseline: benchmark Portfolio (optional)
        :param start_date: start date for metrics calculation (optional)
        :return: dictionary with metrics
        """
        capitalisation = self.get_capitalisation()
        returns = self.get_returns()
        if start_date is not None:
            capitalisation = capitalisation.loc[capitalisation.index >= start_date]
            returns = returns.loc[returns.index >= start_date]
        cap_3m = capitalisation.loc[capitalisation.index > capitalisation.index.max() - pd.Timedelta(days=93)]
        cap_6m = capitalisation.loc[capitalisation.index > capitalisation.index.max() - pd.Timedelta(days=183)]
        cap_12m = capitalisation.loc[capitalisation.index > capitalisation.index.max() - pd.Timedelta(days=365)]
        cap_3y = capitalisation.loc[capitalisation.index > capitalisation.index.max() - pd.Timedelta(days=365 * 3)]
        profit = self.cash + capitalisation.iloc[-1] - capitalisation.iloc[0]
        perf_metrics = {
            "start_date": returns.index[0],
            "start_value": capitalisation.iloc[0],
            "end_date": returns.index[-1],
            "end_value": capitalisation.iloc[-1],
            "profit": profit,
            "profitability": profit / capitalisation.iloc[0],
            "hedge_cost": self.hedge_cost,
            "profit_with_hedge": profit - self.hedge_cost,
            "profitability_with_hedge": (profit - self.hedge_cost) / capitalisation.iloc[0],
            "volatility_3m": metrics.volatility(cap_3m),
            "volatility_6m": metrics.volatility(cap_6m),
            "volatility_12m": metrics.volatility(cap_12m),
            "volatility_3y": metrics.volatility(cap_3y),
            "sharpe": metrics.sharpe_ratio(returns, daily_risk_free_rate=0.0),
            "sortino": metrics.sortino(returns),
            "max_drawdown": metrics.max_drawdown(returns),
            "upside_capture_ratio": None,
            "downside_capture_ratio": None,
            "alpha": None,
            "beta": None,
            "tracking_error": None,
        }
        if baseline:
            benchmark_returns = baseline.get_returns()
            if start_date is not None:
                benchmark_returns = benchmark_returns.loc[benchmark_returns.index >= start_date]
            perf_metrics.update(
                {
                    "upside_capture_ratio": metrics.upside_capture_ratio(self.returns, benchmark_returns),
                    "downside_capture_ratio": metrics.downside_capture_ratio(self.returns, benchmark_returns),
                    "alpha": metrics.alpha_value(self.returns, benchmark_returns),
                    "beta": metrics.beta_value(self.returns, benchmark_returns),
                    "tracking_error": metrics.tracking_error(self.returns, benchmark_returns),
                }
            )
        return perf_metrics

    def get_capitalisation(self) -> pd.Series:
        """Calculate returns f positions and prices"""
        returns_by_asset = self.positions.mul(self.prices, axis=0).dropna()
        return returns_by_asset.sum(axis=1)

    def get_returns(self) -> pd.Series:
        """Calculate portfolio returns"""
        return self.capitalisation.pct_change().fillna(0.0)

    def _get_cumulative_return(self) -> pd.Series:
        """Calculate portfolio cumulative returns"""
        return (self.returns + 1).cumprod()

    def _calculate_cash_flow(self) -> None:
        initial_cash = self.start_cash
        if initial_cash is None:
            initial_cash = self.positions.mul(self.prices, axis=0).dropna().sum(axis=1).iloc[0]
        cash_transactions = (
            pd.DataFrame(
                [
                    {
                        "date": row["date"],
                        "value": row["amount"] * self.prices.loc[pd.to_datetime(row["date"]), row["ticker"]] * -1,
                    }
                    for index, row in self.transactions.iterrows()
                ]
            )
            .groupby("date")
            .agg(cash=("value", "sum"))
        )
        self.positions = self.positions.join(cash_transactions, how="left").fillna(0.0)
        self.positions = self.positions.assign(cash=initial_cash + self.positions["cash"].cumsum())
        self.prices = self.prices.assign(cash=1.00)


def build_portfolio_from_transactions(transactions: pd.DataFrame) -> Portfolio:
    """Build portfolio from transactions dataset
    :param transactions: pandas DataFrame of transactions.
           Columns: 'date': date, 'amount': int, 'ticker': str
           if 'amount' positive, transaction - buy, if negative - sell
           Example:
               | date       | amount | ticker  |
               ---------------------------------
               | 2021-05-23 |    15  | AAPL    |
    :return: Portfolio instance
    """
    positions = get_positions(transactions)
    prices = get_prices(positions)
    return Portfolio(positions=positions, prices=prices, transactions=transactions)


def get_positions(transactions: pd.DataFrame) -> pd.DataFrame:
    """Create dataset with daily positions from transactions
    :param transactions: pandas DataFrame of transactions
    :return: pandas DataFrame with daily positions.
    """
    transactions_long = pd.concat(
        [
            pd.DataFrame(
                {"amount": [row["amount"]], "ticker": [row["ticker"]]},
                index=pd.Series(pd.date_range(row["date"], pd.Timestamp.today() - pd.Timedelta(days=1)), name="date"),
            ).reset_index()
            for index, row in transactions.iterrows()
        ]
    )
    return transactions_long.pivot_table(index="date", columns="ticker", values="amount", aggfunc="sum", fill_value=0)


def get_prices(positions: pd.DataFrame) -> pd.DataFrame:
    """Get prices for positions
    :param positions: pandas DataFrame of positions (number of shares per asset).
    :return: Pandas DataFrame of prices.
    """
    start = positions.index.min().date()
    end = positions.index.max().date()
    prices = pd.DataFrame(index=positions.index)
    for ticker in positions.columns:
        prices[ticker] = read_prices(ticker, start, end)
    return prices


def performance_summary(performance: dict) -> pd.DataFrame:
    """Create pandas DataFrame of performance metrics
    :param performance: dictionary with performance metrics
    :return: pandas DataFrame of performance metrics
    """
    metrics_df = pd.DataFrame(
        {
            "Start Date": [performance["start_date"].date()],
            "End Date": [performance["end_date"].date()],
            "Start Portfolio Value": [f'{performance['start_value']:,.2f}'],
            "End Portfolio Value": [f'{performance['end_value']:,.2f}'],
            "Profit": [f'{performance['profit']:,.2f}'],
            "Profitability": [f'{performance['profitability']*100:.2f} %'],
            "Hedging Cost": [f'{performance['hedge_cost']:,.2f}'],
            "Profit including Hedge Cost": [f'{performance['profit_with_hedge']:,.2f}'],
            "Profitability including Hedge Cost": [f'{performance['profitability_with_hedge'] * 100:.2f} %'],
            "Volatility (3m)": [f'{performance['volatility_3m']*100:.2f} %'],
            "Volatility (6m)": [f'{performance['volatility_6m']*100:.2f} %'],
            "Volatility (12m)": [f'{performance['volatility_12m']*100:.2f} %'],
            "Volatility (3y)": [f'{performance['volatility_3y']*100:.2f} %'],
            "Sharpe Ratio": [f'{performance['sharpe']:.3f}'],
            "Sortino Ratio": [f'{performance['sortino']:.3f}'],
            "Max Drawdown": [f'{performance['max_drawdown']:.3f}'],
            "Upside capture ratio": [f'{performance['upside_capture_ratio']:.3f}'],
            "Downside capture ratio": [f'{performance['downside_capture_ratio']:.3f}'],
            "Alpha": [f'{performance['alpha']:.3f}'],
            "Beta": [f'{performance['beta']:.3f}'],
            "Tracking_error": [f'{performance['tracking_error']:.3f}'],
        }
    ).T
    metrics_df.columns = ["Value"]
    return metrics_df
