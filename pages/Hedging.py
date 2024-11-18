"""UI for application
"""

import streamlit as st

from src.simulation.base_simulator import OptionsSimulator
from src.simulation.transformations import filter_non_technology_company
from src.performance.plots import plot_cumulative_returns
from src.performance.portfolio import performance_summary


def get_hedge_simulator():
    """Hedging configuration form"""
    with st.form(key="create_hedge", clear_on_submit=False):
        st.write("Configuration for Simple Hedge Simulator")
        relative_strike = st.number_input("Relative strike price", value=1.00, min_value=0.01)
        option_maturity_months = st.number_input("Option maturity in months", value=12, min_value=1)
        put_new_trigger = st.number_input("Increase factor", value=1.00, min_value=1.00)
        not_buy = st.toggle("Do not buy new options when price increase", False)
        exclude_non_technical_stocks = st.toggle("Exclude non-technical stocks", False)
        submit = st.form_submit_button("Apply hedge to portfolio")
        if submit:
            if not_buy:
                put_new_trigger = None
            simulator = OptionsSimulator(relative_strike, option_maturity_months, put_new_trigger)
            portfolio = st.session_state.portfolio
            if exclude_non_technical_stocks:
                portfolio = filter_non_technology_company(st.session_state.portfolio.transactions)
            st.session_state.hedge_portfolio = simulator.apply_strategy(portfolio)
            st.dataframe(
                simulator.options,
                column_config={
                    "date": st.column_config.DateColumn(label="Date", format="YYYY-MM-DD"),
                    "premium": st.column_config.NumberColumn(label="Premium", format="$%.2f"),
                    "cost": st.column_config.NumberColumn(label="Cost", format="$%.2f"),
                    "strike": st.column_config.NumberColumn(label="Strike", format="$%.2f"),
                },
                use_container_width=True,
            )
            st.write(":green[Hedge applied to portfolio successfully]")
            st.write(":red[Premium estimated using Black-Scholes model]")


def hedge_performance_summary():
    """Build performance summary table"""
    portfolio_performance = performance_summary(st.session_state.portfolio.performance(st.session_state.benchmark))
    hedge_performance = performance_summary(st.session_state.hedge_portfolio.performance(st.session_state.benchmark))
    performance = portfolio_performance.join(hedge_performance, rsuffix="_hedge")
    performance.columns = ["Portfolio Performance", "Hedge Portfolio Performance"]
    return performance


def main():
    """Hedging page"""
    st.set_page_config(page_title="Hedging", page_icon="📈")
    st.title("Base Hedge Simulation")

    if "hedge_portfolio" not in st.session_state:
        st.session_state.hedge_portfolio = None

    get_hedge_simulator()
    if st.session_state.hedge_portfolio is not None:
        st.write(f"Hedge Cost: {st.session_state.hedge_portfolio.hedge_cost:.2f}")
        st.write("Hedged Portfolio Performance")
        st.table(hedge_performance_summary())
        st.plotly_chart(
            plot_cumulative_returns(
                st.session_state.portfolio, st.session_state.benchmark, st.session_state.hedge_portfolio
            )
        )
        st.table(st.session_state.hedge_portfolio.transactions)


if __name__ == "__main__":
    main()
