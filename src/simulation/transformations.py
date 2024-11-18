"""Transformation module."""

import pandas as pd

from src.data.read import read_sector
from src.performance.portfolio import Portfolio, build_portfolio_from_transactions


def filter_non_technology_company(transactions: pd.DataFrame) -> Portfolio:
    """Remove non technology companies transactions.
    
    :param transactions: pandas DataFrame with transactions
    :return: Portfolio without non technology companies
    """
    tickers = transactions["ticker"].unique().tolist()
    sectors = read_sector(tickers)
    technology_sectors = ["Technology"]
    technology_companies = sectors[sectors["sector"].isin(technology_sectors)]["ticker"].unique().tolist()
    technology_transactions = transactions[transactions["ticker"].isin(technology_companies)].copy()
    return build_portfolio_from_transactions(technology_transactions)
