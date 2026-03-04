"""
Market Scanner — Collects price data, macro indicators, volatility, and produces
a structured market state representation.
"""
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import logging
import json

from agent.config import (
    UNIVERSE, LOOKBACK_DAYS, SHORT_LOOKBACK, FRED_API_KEY, FRED_SERIES,
    EQUITY_TICKERS, BOND_TICKERS, ALT_TICKERS, BENCHMARK_TICKER
)

logger = logging.getLogger(__name__)


def fetch_prices(tickers=None, period_days=None):
    """Fetch historical prices for universe. Returns DataFrame of adjusted close."""
    if tickers is None:
        tickers = list(UNIVERSE.keys())
    if period_days is None:
        period_days = LOOKBACK_DAYS

    end = datetime.now()
    start = end - timedelta(days=period_days + 10)  # buffer for weekends

    all_tickers = tickers + ["^VIX", "^TNX", "^FVX", "^IRX"]
    unique_tickers = list(set(all_tickers))

    logger.info(f"Fetching prices for {len(unique_tickers)} tickers...")
    try:
        data = yf.download(unique_tickers, start=start.strftime("%Y-%m-%d"),
                           end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if isinstance(data.columns, pd.MultiIndex):
            prices = data["Close"]
        else:
            prices = data[["Close"]].rename(columns={"Close": unique_tickers[0]})
        prices = prices.dropna(how="all").ffill()
        logger.info(f"Fetched {len(prices)} days of data")
        return prices
    except Exception as e:
        logger.error(f"Price fetch failed: {e}")
        return pd.DataFrame()


def fetch_fred_data():
    """Fetch macro data from FRED. Returns dict of latest values."""
    if not FRED_API_KEY:
        logger.warning("No FRED API key — skipping macro data")
        return {}

    try:
        from fredapi import Fred
        fred = Fred(api_key=FRED_API_KEY)
        macro = {}
        for series_id, name in FRED_SERIES.items():
            try:
                data = fred.get_series(series_id, observation_start=(datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"))
                if data is not None and len(data) > 0:
                    macro[series_id] = {
                        "name": name,
                        "latest": float(data.iloc[-1]),
                        "prev": float(data.iloc[-2]) if len(data) > 1 else None,
                        "change": float(data.iloc[-1] - data.iloc[-2]) if len(data) > 1 else 0,
                    }
            except Exception as e:
                logger.warning(f"FRED series {series_id} failed: {e}")
        return macro
    except ImportError:
        logger.warning("fredapi not installed — skipping FRED data")
        return {}


def compute_market_signals(prices):
    """Compute derived signals from price data."""
    signals = {}
    tickers = [t for t in UNIVERSE.keys() if t in prices.columns]

    if len(tickers) == 0:
        return signals

    returns = prices[tickers].pct_change().dropna()
    if len(returns) < 5:
        return signals

    # --- VIX ---
    if "^VIX" in prices.columns:
        vix_series = prices["^VIX"].dropna()
        signals["vix_current"] = float(vix_series.iloc[-1]) if len(vix_series) > 0 else 20.0
        signals["vix_ma20"] = float(vix_series.tail(20).mean()) if len(vix_series) >= 20 else signals["vix_current"]
        signals["vix_percentile"] = float((vix_series.iloc[-1] - vix_series.min()) / (vix_series.max() - vix_series.min())) if len(vix_series) > 1 else 0.5
    else:
        signals["vix_current"] = 20.0
        signals["vix_ma20"] = 20.0
        signals["vix_percentile"] = 0.5

    # --- Yield curve (10Y - 2Y proxy) ---
    if "^TNX" in prices.columns and "^FVX" in prices.columns:
        tnx = prices["^TNX"].dropna()
        fvx = prices["^FVX"].dropna()
        if len(tnx) > 0 and len(fvx) > 0:
            signals["yield_spread"] = float(tnx.iloc[-1] - fvx.iloc[-1])
        else:
            signals["yield_spread"] = 0.0
    else:
        signals["yield_spread"] = 0.0

    # --- Broad market momentum ---
    if BENCHMARK_TICKER in prices.columns:
        spy = prices[BENCHMARK_TICKER].dropna()
        if len(spy) >= SHORT_LOOKBACK:
            signals["spy_momentum_63d"] = float(spy.iloc[-1] / spy.iloc[-SHORT_LOOKBACK] - 1)
        else:
            signals["spy_momentum_63d"] = 0.0
        if len(spy) >= 21:
            signals["spy_momentum_21d"] = float(spy.iloc[-1] / spy.iloc[-21] - 1)
        else:
            signals["spy_momentum_21d"] = 0.0
    else:
        signals["spy_momentum_63d"] = 0.0
        signals["spy_momentum_21d"] = 0.0

    # --- Sector momentum ---
    sector_mom = {}
    for t in tickers:
        series = prices[t].dropna()
        if len(series) >= SHORT_LOOKBACK:
            sector_mom[t] = float(series.iloc[-1] / series.iloc[-SHORT_LOOKBACK] - 1)
    signals["sector_momentum"] = sector_mom

    # --- Cross-asset signals ---
    equity_rets = returns[[t for t in EQUITY_TICKERS if t in returns.columns]]
    bond_rets = returns[[t for t in BOND_TICKERS if t in returns.columns]]

    if len(equity_rets.columns) > 0 and len(equity_rets) >= 5:
        signals["equity_avg_return_5d"] = float(equity_rets.tail(5).mean().mean())
        signals["equity_volatility_21d"] = float(equity_rets.tail(21).std().mean() * np.sqrt(252)) if len(equity_rets) >= 21 else 0.15
    else:
        signals["equity_avg_return_5d"] = 0.0
        signals["equity_volatility_21d"] = 0.15

    if len(bond_rets.columns) > 0 and len(bond_rets) >= 5:
        signals["bond_avg_return_5d"] = float(bond_rets.tail(5).mean().mean())
    else:
        signals["bond_avg_return_5d"] = 0.0

    # --- Correlation regime ---
    if len(equity_rets.columns) > 0 and len(bond_rets.columns) > 0 and len(returns) >= 21:
        eq_mean = equity_rets.tail(21).mean(axis=1)
        bd_mean = bond_rets.tail(21).mean(axis=1)
        if len(eq_mean) > 5 and len(bd_mean) > 5:
            signals["equity_bond_corr_21d"] = float(eq_mean.corr(bd_mean))
        else:
            signals["equity_bond_corr_21d"] = -0.3
    else:
        signals["equity_bond_corr_21d"] = -0.3

    # --- Market breadth ---
    if len(equity_rets.columns) > 0 and len(equity_rets) >= 5:
        weekly_ret = equity_rets.tail(5).sum()
        signals["breadth_positive"] = float((weekly_ret > 0).sum() / len(weekly_ret))
    else:
        signals["breadth_positive"] = 0.5

    # --- Realized vol vs implied vol ---
    if BENCHMARK_TICKER in returns.columns and len(returns) >= 21:
        realized_vol = float(returns[BENCHMARK_TICKER].tail(21).std() * np.sqrt(252) * 100)
        signals["vol_risk_premium"] = signals["vix_current"] - realized_vol
    else:
        signals["vol_risk_premium"] = 0.0

    return signals


def compute_return_covariance(prices, tickers=None, halflife=None):
    """Compute EWMA covariance matrix for allocation."""
    from agent.config import EWMA_HALFLIFE
    if halflife is None:
        halflife = EWMA_HALFLIFE
    if tickers is None:
        tickers = [t for t in UNIVERSE.keys() if t in prices.columns]

    returns = prices[tickers].pct_change().dropna()
    if len(returns) < 10:
        return pd.DataFrame(np.eye(len(tickers)) * 0.04, index=tickers, columns=tickers), returns

    ewma_cov = returns.ewm(halflife=halflife).cov()
    last_date = returns.index[-1]
    cov_matrix = ewma_cov.loc[last_date]
    return cov_matrix, returns


def scan_market():
    """Main scan function. Returns structured market state dict."""
    logger.info("=== MARKET SCAN START ===")

    prices = fetch_prices()
    if prices.empty:
        logger.error("No price data available")
        return {"error": "no_data", "timestamp": datetime.now().isoformat()}

    signals = compute_market_signals(prices)
    macro = fetch_fred_data()

    tickers = [t for t in UNIVERSE.keys() if t in prices.columns]
    cov_matrix, returns = compute_return_covariance(prices, tickers)

    # Expected returns (simple momentum-based estimate)
    expected_returns = {}
    for t in tickers:
        if t in prices.columns:
            series = prices[t].dropna()
            if len(series) >= SHORT_LOOKBACK:
                mom = series.iloc[-1] / series.iloc[-SHORT_LOOKBACK] - 1
                expected_returns[t] = mom / (SHORT_LOOKBACK / 252)  # Annualize
            else:
                expected_returns[t] = 0.0

    state = {
        "timestamp": datetime.now().isoformat(),
        "available_tickers": tickers,
        "signals": signals,
        "macro": macro,
        "expected_returns": expected_returns,
        "covariance_available": len(cov_matrix) > 0,
        "data_quality": {
            "tickers_fetched": len(tickers),
            "tickers_requested": len(UNIVERSE),
            "days_of_data": len(prices),
        }
    }

    logger.info(f"Scan complete: {len(tickers)} tickers, VIX={signals.get('vix_current', 'N/A')}")
    return state
