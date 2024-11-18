"""
Utility functions
"""

from datetime import date, timedelta


def get_next_friday(dt: date) -> str:
    """Define next friday date from the provided date"""
    day_of_week = dt.weekday()
    if day_of_week >= 4:
        day_of_week -= 7
    return (dt + timedelta(days=4 - day_of_week)).strftime("%Y-%m-%d")
