"""UI for application."""

import streamlit as st

from src.performance.plots import plot_cumulative_returns
from src.performance.portfolio import performance_summary


def main():
    """Portfolio page"""
    st.set_page_config(page_title="Portfolio", page_icon="📈")
    st.title("Portfolio Analysis")
    st.write("Portfolio Performance Summary")
    if "portfolio" not in st.session_state:
        st.session_state.portfolio = None
    if st.session_state.portfolio is None:
        st.write("Please create a portfolio on Transaction tab")
        return
    st.table(performance_summary(st.session_state.performance))

    st.plotly_chart(plot_cumulative_returns(st.session_state.portfolio, st.session_state.benchmark))


if __name__ == "__main__":
    main()
