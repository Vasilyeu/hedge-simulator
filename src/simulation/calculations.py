"""Hedging calculations module."""

import numpy as np
import scipy.stats as si


class BlackScholesModel:
    """Black-Scholes Model for option premium calculations."""

    def __init__(self, S: float, K: float, T: float, r: float, sigma: float):
        """Initializes Black-Scholes Model parameters.

        Args:
            S (float): Underlying asset price
            K (float): Option strike price
            T (float): Time to expiration in years
            r (float): Risk-free interest rate
            sigma (float): Volatility of the underlying asset
        """
        self.S = S
        self.K = K
        self.T = T
        self.r = r
        self.sigma = sigma

    def d1(self):
        """Calculates d1 for Black-Scholes model."""
        return (np.log(self.S / self.K) + (self.r + 0.5 * self.sigma**2) * self.T) / (self.sigma * np.sqrt(self.T))

    def d2(self):
        """Calculates d2 for Black-Scholes model."""
        return self.d1() - self.sigma * np.sqrt(self.T)

    def call_option_price(self):
        """Calculates call option price (premium) for Black-Scholes model."""
        return self.S * si.norm.cdf(self.d1(), 0.0, 1.0) - self.K * np.exp(-self.r * self.T) * si.norm.cdf(
            self.d2(), 0.0, 1.0
        )

    def put_option_price(self):
        """Calculates put option price for Black-Scholes model."""
        return self.K * np.exp(-self.r * self.T) * si.norm.cdf(-self.d2(), 0.0, 1.0) - self.S * si.norm.cdf(
            -self.d1(), 0.0, 1.0
        )
