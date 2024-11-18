"""Module for reading data.
"""

import datetime

import duckdb
import pandas as pd
import yfinance as yf
from pyrate_limiter import Duration, Limiter, RequestRate
from requests import Session
from requests_cache import CacheMixin, SQLiteCache
from requests_ratelimiter import LimiterMixin, MemoryQueueBucket


class CachedLimiterSession(CacheMixin, LimiterMixin, Session):  # pylint: disable=abstract-method
    """Request session with caching and rate limiting"""


class YahooFinanceReader:
    """Yahoo Finance API Reader"""

    def __init__(self):
        self.session = self._get_session()

    def get_stock_prices(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Get prices from Yahoo Finance API"""
        ticker_data = yf.Ticker(ticker, session=self.session)
        history = ticker_data.history(start=start_date, end=end_date, auto_adjust=True)
        history = history.assign(ticker=ticker).reset_index()
        return history.reset_index()

    def get_stock_sector(self, ticker: str) -> dict[str, str]:
        """Get company sector from Yahoo Finance"""
        ticker_data = yf.Ticker(ticker, session=self.session)
        return {"ticker": ticker, "sector": ticker_data.info["sector"]}

    def _get_session(self):
        """Create session for API calls"""
        return CachedLimiterSession(
            limiter=Limiter(RequestRate(2, Duration.SECOND * 5)),
            bucket_class=MemoryQueueBucket,
            backend=SQLiteCache("data/yfinance.cache"),
        )


class LocalReader:
    """Local DB wrapper"""

    def __init__(self):
        self.local_file = "data/jinbu.duckdb"
        self.con = duckdb.connect(database=self.local_file, read_only=False)
        self._create_tables_if_not_exists()

    def _create_tables_if_not_exists(self):
        """Create required tables if they don't exist."""
        self.con.execute(
            
                "CREATE TABLE IF NOT EXISTS stocks "
                "(ticker VARCHAR, date DATE, open FLOAT, close FLOAT, high FLOAT, low FLOAT, PRIMARY KEY (ticker, date))"
            
        )
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS stocks_info (ticker VARCHAR, sector VARCHAR, PRIMARY KEY (ticker))"
        )

    def check_ticker(self, ticker) -> list:
        """Check the first and last available dates for ticker"""
        return self.con.sql(f"SELECT MIN(date), MAX(date) FROM stocks WHERE ticker = '{ticker}'").fetchall()[0]

    def save_prices(self, data: pd.DataFrame):
        """Save prices to DB"""
        df = data[["ticker", "Date", "Open", "Close", "High", "Low"]]  # pylint: disable=unused-variable)
        self.con.execute("INSERT OR IGNORE INTO stocks SELECT * FROM df")

    def get_prices(self, ticker: str, start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
        """Read prices from DB"""
        return self.con.sql(
            
                f"SELECT date, close FROM stocks "
                f"WHERE ticker = '{ticker}' AND date BETWEEN '{start_date}' AND '{end_date}' ORDER BY date"
            
        ).df()

    def save_sector(self, data: dict[str, str]) -> None:
        """Save sector info in DB"""
        self.con.execute("INSERT OR IGNORE INTO stocks_info VALUES (?, ?)", [data["ticker"], data["sector"]])

    def get_sector(self, tickers: list[str]) -> pd.DataFrame:
        """Read sector info from DB"""
        return self.con.execute(
            "SELECT ticker, sector FROM stocks_info WHERE ticker IN (SELECT UNNEST(?))", [tickers]
        ).df()


def read_prices(ticker: str, start_date: datetime.date, end_date: datetime.date) -> pd.Series:
    """Read prices for the ticker.
    First, try to read prices from a local database. If data is absent - get data from Yahoo Finance API
    :param ticker: string, market ticker
    :param start_date: first date to read
    :param end_date: last date to read
    :return: pandas Series of prices
    """
    local_reader = LocalReader()
    min_date, max_date = local_reader.check_ticker(ticker)
    yfinance_reader = YahooFinanceReader()
    if min_date is None:
        data_from_api = yfinance_reader.get_stock_prices(
            ticker, start_date=start_date.strftime("%Y-%m-%d"), end_date=end_date.strftime("%Y-%m-%d")
        )
        local_reader.save_prices(data_from_api)
    else:
        if min_date > start_date:
            data_from_api_old = yfinance_reader.get_stock_prices(
                ticker, start_date=start_date.strftime("%Y-%m-%d"), end_date=min_date.strftime("%Y-%m-%d")
            )
            local_reader.save_prices(data_from_api_old)
        if max_date < end_date:
            data_from_api_new = yfinance_reader.get_stock_prices(
                ticker,
                start_date=(max_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
                end_date=(end_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
            )
            local_reader.save_prices(data_from_api_new)
    prices = local_reader.get_prices(ticker, start_date, end_date)
    return prices.drop_duplicates().set_index("date")["close"]


def read_sector(tickers: list[str]) -> pd.DataFrame:
    """Read industry of the company
    :param tickers: list of strings, companies' market tickers
    :return: pandas DataFrame with tickers and industries
    """
    local_reader = LocalReader()
    sectors = local_reader.get_sector(tickers)
    missed_tickers = [x for x in tickers if x not in sectors["ticker"].tolist()]
    if len(missed_tickers) > 0:
        yfinance_reader = YahooFinanceReader()
        for ticker in missed_tickers:
            sector_from_api = yfinance_reader.get_stock_sector(ticker)
            local_reader.save_sector(sector_from_api)
    return local_reader.get_sector(tickers)
