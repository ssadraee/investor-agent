"""
Evaluator — Computes weekly performance, risk metrics, and benchmark comparisons.
"""
import numpy as np
import pandas as pd
import yfinance as yf
import logging
from datetime import datetime, timedelta

from agent.config import UNIVERSE, BENCHMARK_TICKER, INITIAL_CAPITAL
from agent.utils import (
    compute_sharpe, compute_sortino, compute_max_drawdown,
    compute_volatility, apply_transaction_costs, pct_fmt
)
from agent.allocator import compute_equal_weight_benchmark, compute_risk_parity_benchmark
from agent.scanner import compute_return_covariance
from agent import storage

logger = logging.getLogger(__name__)


def evaluate_week(week_id):
    """
    Evaluate portfolio performance for the given week.
    Returns metrics dict.
    """
    portfolio = storage.get_latest_portfolio()
    if not portfolio:
        logger.error("No portfolio found for evaluation")
        return {"error": "no_portfolio"}

    allocation = portfolio["allocation"]
    non_cash = {k: v for k, v in allocation.items() if k != "CASH"}
    tickers = list(non_cash.keys())

    if not tickers:
        return _empty_metrics(week_id)

    # Fetch this week's prices
    end = datetime.now()
    start = end - timedelta(days=12)  # Buffer to capture Monday open
    all_tickers = tickers + [BENCHMARK_TICKER]
    unique = list(set(all_tickers))

    try:
        data = yf.download(unique, start=start.strftime("%Y-%m-%d"),
                           end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if isinstance(data.columns, pd.MultiIndex):
            prices = data["Close"].dropna(how="all").ffill()
        else:
            prices = data[["Close"]].rename(columns={"Close": unique[0]}).ffill()
    except Exception as e:
        logger.error(f"Price fetch for evaluation failed: {e}")
        return _empty_metrics(week_id)

    if len(prices) < 2:
        logger.warning("Insufficient price data for evaluation")
        return _empty_metrics(week_id)

    # --- Portfolio return ---
    returns_df = prices.pct_change().dropna()
    if len(returns_df) == 0:
        return _empty_metrics(week_id)

    weekly_returns = returns_df.sum()  # Approximate: sum of daily returns over the week

    port_return = 0.0
    for t, w in non_cash.items():
        if t in weekly_returns.index:
            port_return += w * weekly_returns[t]
    cash_w = allocation.get("CASH", 0)
    # Cash earns nothing in simulation

    # Transaction costs (compare with previous allocation)
    prev_alloc = _get_previous_allocation(week_id)
    tx_cost = apply_transaction_costs(prev_alloc, allocation, INITIAL_CAPITAL)
    port_return -= tx_cost / INITIAL_CAPITAL

    # --- SPY benchmark ---
    spy_return = float(weekly_returns.get(BENCHMARK_TICKER, 0))

    # --- Equal weight benchmark ---
    ew_alloc = compute_equal_weight_benchmark(tickers)
    ew_return = sum(ew_alloc.get(t, 0) * weekly_returns.get(t, 0) for t in ew_alloc)

    # --- Risk parity benchmark ---
    try:
        long_prices = yf.download(tickers, period="6mo", progress=False, auto_adjust=True)
        if isinstance(long_prices.columns, pd.MultiIndex):
            lp = long_prices["Close"].dropna(how="all").ffill()
        else:
            lp = long_prices[["Close"]].rename(columns={"Close": tickers[0]}).ffill()
        cov_matrix, _ = compute_return_covariance(lp, tickers)
        rp_alloc = compute_risk_parity_benchmark(cov_matrix, tickers)
    except Exception:
        rp_alloc = ew_alloc
    rp_return = sum(rp_alloc.get(t, 0) * weekly_returns.get(t, 0) for t in rp_alloc)

    # --- Cumulative tracking ---
    all_perf = storage.get_all_performance()
    historical_returns = [p["weekly_return"] for p in all_perf if p.get("weekly_return") is not None]
    historical_returns.append(port_return)

    cumulative = np.cumprod([1 + r for r in historical_returns])
    cum_return = float(cumulative[-1] - 1) if len(cumulative) > 0 else port_return

    # --- Risk metrics ---
    sharpe = compute_sharpe(historical_returns)
    sortino = compute_sortino(historical_returns)
    max_dd = compute_max_drawdown(cumulative)
    vol = compute_volatility(historical_returns)

    metrics = {
        "week_id": week_id,
        "weekly_return": round(float(port_return), 6),
        "cumulative_return": round(cum_return, 6),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "max_drawdown": round(max_dd, 6),
        "volatility": round(vol, 4),
        "benchmark_spy": round(float(spy_return), 6),
        "benchmark_ew": round(float(ew_return), 6),
        "benchmark_rp": round(float(rp_return), 6),
        "transaction_cost": round(tx_cost, 2),
        "portfolio_value": round(INITIAL_CAPITAL * (1 + cum_return), 2),
    }

    logger.info(f"Week {week_id}: return={pct_fmt(port_return)}, "
                f"SPY={pct_fmt(spy_return)}, Sharpe={sharpe:.2f}")

    return metrics


def _get_previous_allocation(current_week_id):
    """Get the allocation from the previous week."""
    all_portfolios = storage.get_all_portfolios()
    for p in reversed(all_portfolios):
        import json
        alloc = json.loads(p["allocation"]) if isinstance(p["allocation"], str) else p["allocation"]
        if p["week_id"] < current_week_id:
            return alloc
    return {}


def _empty_metrics(week_id):
    return {
        "week_id": week_id,
        "weekly_return": 0.0,
        "cumulative_return": 0.0,
        "sharpe": 0.0,
        "sortino": 0.0,
        "max_drawdown": 0.0,
        "volatility": 0.0,
        "benchmark_spy": 0.0,
        "benchmark_ew": 0.0,
        "benchmark_rp": 0.0,
        "transaction_cost": 0.0,
        "portfolio_value": INITIAL_CAPITAL,
    }
