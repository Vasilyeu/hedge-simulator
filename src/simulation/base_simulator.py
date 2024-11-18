"""
Put options simulator
"""

from datetime import date
from queue import PriorityQueue

import pandas as pd

from src.data.read import read_prices
from src.performance.metrics import volatility
from src.performance.portfolio import Portfolio, get_positions
from src.simulation.calculations import BlackScholesModel
from src.utils.utils import get_next_friday


class OptionsSimulator:
    """Put Option Simulator"""

    def __init__(
        self, relative_strike_price: float, maturity_months: int, new_option_trigger: float | None = None
    ) -> None:
        self.relative_strike_price = relative_strike_price
        self.maturity_months = maturity_months
        self.new_option_trigger = new_option_trigger
        self.cost = 0
        self.cash = 0
        self.options = None

    def apply_strategy(self, portfolio: Portfolio) -> Portfolio:
        """Apply strategy to portfolio"""
        puts_options, new_transactions = self.get_put_options(portfolio)
        self.cost = puts_options["cost"].sum()
        self.options = puts_options
        put_strike_prices = _get_put_prices(puts_options)
        adjusted_prices = pd.concat([portfolio.prices, put_strike_prices]).groupby(level=0).max()
        adjusted_prices = adjusted_prices.loc[adjusted_prices.index.isin(portfolio.returns.index)].drop(columns="cash")
        new_positions = get_positions(new_transactions)
        hedge_portfolio = Portfolio(positions=new_positions, prices=adjusted_prices, transactions=new_transactions)
        hedge_portfolio.hedge_cost = self.cost
        hedge_portfolio.cash = self.cash
        return hedge_portfolio

    def get_put_options(self, portfolio: Portfolio) -> (pd.DataFrame, pd.DataFrame):
        """Get put options for portfolio"""
        put_options = []
        new_transactions = []
        buy_transactions = portfolio.transactions[portfolio.transactions["amount"] > 0]
        sell_transactions = portfolio.transactions[portfolio.transactions["amount"] <= 0]
        for _, transaction in buy_transactions.iterrows():
            ticker = transaction["ticker"]
            all_options = PriorityQueue()
            option = self._process_one_transaction(transaction.to_dict(), portfolio)
            all_options.put((option["date"], option))
            put_options.append(option)
            new_transactions.append(transaction.to_dict())
            current_position = transaction["amount"]
            current_options = option["amount"]
            current_max_price = portfolio.prices.loc[pd.Timestamp(transaction["date"]), ticker]
            next_expire_option = all_options.get()[1]
            current_min_expire = pd.Timestamp(next_expire_option["expire"])
            prices = portfolio.prices.copy().dropna().iloc[1:]
            for index_date, current_price in zip(prices.index, prices[ticker].to_numpy()):
                if index_date == current_min_expire:
                    if current_price < next_expire_option["strike"]:
                        sold_money = next_expire_option["strike"] * next_expire_option["amount"]
                        number_of_new_shares = int(sold_money / current_price)
                        self.cash += sold_money - number_of_new_shares * current_price
                        addition_shares = number_of_new_shares - next_expire_option["amount"]
                        current_options -= next_expire_option["amount"]
                        if addition_shares > 0:
                            new_transactions.append(
                                {
                                    "date": (index_date - pd.Timedelta(days=1)).date(),
                                    "ticker": ticker,
                                    "amount": next_expire_option["amount"] * -1,
                                }
                            )
                            new_transactions.append(
                                {"date": index_date.date(), "ticker": ticker, "amount": number_of_new_shares}
                            )
                            current_position += addition_shares
                        required_options = current_position - current_options
                        if required_options > 0:
                            virtual_buy = {"date": index_date, "ticker": ticker, "amount": required_options}
                            option = self._process_one_transaction(virtual_buy, portfolio)
                            all_options.put((option["date"], option))
                            put_options.append(option)
                            current_options = current_options + required_options
                    else:
                        current_options -= next_expire_option["amount"]
                        required_options = current_position - current_options
                        if required_options > 0:
                            virtual_buy = {"date": index_date, "ticker": ticker, "amount": required_options}
                            option = self._process_one_transaction(virtual_buy, portfolio)
                            put_options.append(option)
                            all_options.put((option["date"], option))
                            current_options = current_options + required_options
                    next_expire_option = all_options.get()[1]
                    current_min_expire = pd.Timestamp(next_expire_option["expire"])
                if (
                    self.new_option_trigger is not None
                    and (current_max_price * self.new_option_trigger) < current_price
                ):
                    new_option_buy = {"date": index_date, "ticker": ticker, "amount": current_position}
                    new_option = self._process_one_transaction(new_option_buy, portfolio)
                    put_options.append(new_option)
                    all_options.put((new_option["date"], new_option))
                    current_options = current_options + current_position
                    current_max_price = current_price * self.new_option_trigger
                    all_options.put((next_expire_option["date"], next_expire_option))
                    next_expire_option = all_options.get()[1]
                    current_min_expire = pd.Timestamp(next_expire_option["expire"])
        new_transactions_df = pd.DataFrame(new_transactions)
        if len(sell_transactions) > 0:
            new_transactions_df = pd.concat([new_transactions_df, sell_transactions]).sort_values("date")
        return pd.DataFrame(put_options), new_transactions_df

    def _process_one_transaction(self, transaction: dict, portfolio: Portfolio) -> (pd.DataFrame, pd.DataFrame):
        """Process one transaction"""
        ticker = transaction["ticker"]
        tr_date = pd.Timestamp(transaction["date"])
        price = portfolio.prices.loc[tr_date, ticker]
        prices = read_prices(ticker, (tr_date - pd.Timedelta(days=366)).date(), tr_date.date())
        vol = volatility(prices)
        premium = BlackScholesModel(
            S=price, K=price * self.relative_strike_price, T=self.maturity_months / 12, r=0.0, sigma=vol
        ).put_option_price()
        return self._get_put_option(ticker, price, transaction["amount"], tr_date, premium)

    def _get_put_option(self, ticker: str, price: float, amount: int, transaction_date: date, premium: float) -> dict:
        """Get a put option"""
        expire = transaction_date + pd.Timedelta(days=int(self.maturity_months * 30.5))
        return {
            "ticker": ticker,
            "date": transaction_date,
            "expire": get_next_friday(expire),
            "amount": amount,
            "premium": premium,
            "cost": amount * premium,
            "strike": price * self.relative_strike_price,
        }


def _get_put_prices(put_transactions: pd.DataFrame) -> pd.DataFrame:
    """Get put prices"""
    return (
        pd.concat(
            [
                pd.DataFrame(
                    data={row["ticker"]: [row["strike"]]},
                    index=pd.Series(
                        pd.date_range(pd.Timestamp(row["date"]), pd.Timestamp(row["expire"]) - pd.Timedelta(days=1)),
                        name="date",
                    ),
                )
                for index, row in put_transactions.iterrows()
            ],
            axis=1,
        )
        .groupby(level=0, axis=1)
        .max()
    )
