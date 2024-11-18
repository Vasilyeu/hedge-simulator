"""UI for application
"""

import pandas as pd
import streamlit as st


def main():
    """App Main page"""
    st.set_page_config(page_title="Main", page_icon="📈")
    st.title("Portfolio Analysis")
    st.markdown(
        """
    Portfolio Analytics and Hedging Simulator  
    How to use:  
    - Enter transactions in Transaction tab  
    - Review Portfolio performance on Portfolio tab  
    - Simulate Hedging using Put Options on Hedging tab   
    """
    )
    if "transactions" not in st.session_state:
        st.session_state.transactions = pd.DataFrame(columns=["date", "amount", "ticker"])

    st.write("Current transactions")
    st.write(st.session_state.transactions)


if __name__ == "__main__":
    main()
