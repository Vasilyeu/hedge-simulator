"""Page for transaction management."""

import datetime

import pandas as pd
import streamlit as st

from src.performance.portfolio import build_portfolio_from_transactions


def build_portfolio_with_benchmark(transactions: pd.DataFrame, benchmark_ticker: str) -> None:
    """Build portfolio from transactions and calculate performance compared to benchmark.

    Save portfolio, benchmark portfolio and performance table in session state
    :param transactions: pandas DataFrame with transactions
    :param benchmark_ticker: string, benchmark ticker
    """
    portfolio = build_portfolio_from_transactions(transactions)
    min_date = transactions.date.min()
    benchmark_transactions = pd.DataFrame({"date": [min_date], "amount": [1], "ticker": [benchmark_ticker]})
    benchmark_portfolio = build_portfolio_from_transactions(benchmark_transactions)
    st.session_state.portfolio = portfolio
    st.session_state.benchmark = benchmark_portfolio
    st.session_state.performance = portfolio.performance(benchmark_portfolio)


def clear_portfolio() -> None:
    """Clear portfolio button."""
    st.session_state.portfolio = None
    st.session_state.benchmark = None
    st.session_state.performance = {}
    st.session_state.transactions = pd.DataFrame(columns=["date", "amount", "ticker"])
    st.session_state.hedge_portfolio = None


def add_transaction():
    """Add a transaction form."""
    with st.form(key="add_transaction", clear_on_submit=False):
        st.write("Add transaction to portfolio")
        date = st.date_input("Date", datetime.date.today())
        ticker = st.text_input("Ticker", "AAPL")
        amount = st.number_input("Number of shares (Positive value for buy transaction, negative - for sell)", value=10)
        submit = st.form_submit_button("Add transaction")
        one_transaction = pd.DataFrame({"date": [date], "amount": [amount], "ticker": [ticker]})
        if submit:
            st.session_state.transactions = pd.concat(
                [st.session_state.transactions, one_transaction], ignore_index=True
            )
        st.write("Current transaction")
        st.write(st.session_state.transactions)


def build_portfolio():
    """Build portfolio button."""
    with st.form(key="build_portfolio", clear_on_submit=False):
        st.write("Build portfolio from transactions")
        benchmark_ticker = st.text_input("Benchmark Ticker", "SPY")
        submit = st.form_submit_button("Build portfolio")
        if submit:
            build_portfolio_with_benchmark(st.session_state.transactions, benchmark_ticker)
            st.write(":green[Portfolio build successfully]")


def main():
    """Transactions page."""
    if "portfolio" not in st.session_state:
        st.session_state.portfolio = None
        st.session_state.benchmark = None
        st.session_state.performance = {}

    if "transactions" not in st.session_state:
        st.session_state.transactions = pd.DataFrame(columns=["date", "amount", "ticker"])

    st.set_page_config(page_title="Transactions management", page_icon="📈")
    st.markdown("# Transactions")
    add_transaction()
    build_portfolio()
    st.button("Clear portfolio", on_click=clear_portfolio)


if __name__ == "__main__":
    main()
