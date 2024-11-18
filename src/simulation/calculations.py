"""Hedging calculations module
"""

import numpy as np
import scipy.stats as si


class BlackScholesModel:
    """Black-Scholes Model for option premium calculations"""

    def __init__(self, S, K, T, r, sigma):
        self.S = S  # Underlying asset price
        self.K = K  # Option strike price
        self.T = T  # Time to expiration in years
        self.r = r  # Risk-free interest rate
        self.sigma = sigma  # Volatility of the underlying asset

    def d1(self):
        """Calculates d1 for Black-Scholes model"""
        return (np.log(self.S / self.K) + (self.r + 0.5 * self.sigma**2) * self.T) / (self.sigma * np.sqrt(self.T))

    def d2(self):
        """Calculates d2 for Black-Scholes model"""
        return self.d1() - self.sigma * np.sqrt(self.T)

    def call_option_price(self):
        """Calculates call option price (premium) for Black-Scholes model"""
        return self.S * si.norm.cdf(self.d1(), 0.0, 1.0) - self.K * np.exp(-self.r * self.T) * si.norm.cdf(
            self.d2(), 0.0, 1.0
        )

    def put_option_price(self):
        """Calculates put option price for Black-Scholes model"""
        return self.K * np.exp(-self.r * self.T) * si.norm.cdf(-self.d2(), 0.0, 1.0) - self.S * si.norm.cdf(
            -self.d1(), 0.0, 1.0
        )
