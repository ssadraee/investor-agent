"""
Utility functions — shared across modules.
"""
import numpy as np
from datetime import datetime, timedelta
from agent.config import RISK_FREE_RATE, ANNUALIZATION_FACTOR, TRANSACTION_COST_BPS


def weekly_to_annual(weekly_return):
    return (1 + weekly_return) ** ANNUALIZATION_FACTOR - 1


def compute_sharpe(returns, risk_free=None):
    if risk_free is None:
        risk_free = RISK_FREE_RATE
    if len(returns) < 2:
        return 0.0
    weekly_rf = (1 + risk_free) ** (1 / ANNUALIZATION_FACTOR) - 1
    excess = np.array(returns) - weekly_rf
    if np.std(excess) == 0:
        return 0.0
    return float(np.mean(excess) / np.std(excess) * np.sqrt(ANNUALIZATION_FACTOR))


def compute_sortino(returns, risk_free=None):
    if risk_free is None:
        risk_free = RISK_FREE_RATE
    if len(returns) < 2:
        return 0.0
    weekly_rf = (1 + risk_free) ** (1 / ANNUALIZATION_FACTOR) - 1
    excess = np.array(returns) - weekly_rf
    downside = excess[excess < 0]
    if len(downside) == 0 or np.std(downside) == 0:
        return float(np.mean(excess) * np.sqrt(ANNUALIZATION_FACTOR)) if np.mean(excess) > 0 else 0.0
    return float(np.mean(excess) / np.std(downside) * np.sqrt(ANNUALIZATION_FACTOR))


def compute_max_drawdown(cumulative_returns):
    if len(cumulative_returns) < 2:
        return 0.0
    peak = np.maximum.accumulate(cumulative_returns)
    drawdown = (cumulative_returns - peak) / peak
    return float(np.min(drawdown))


def compute_volatility(returns):
    if len(returns) < 2:
        return 0.0
    return float(np.std(returns) * np.sqrt(ANNUALIZATION_FACTOR))


def apply_transaction_costs(old_weights, new_weights, capital):
    turnover = sum(abs(new_weights.get(k, 0) - old_weights.get(k, 0))
                   for k in set(list(old_weights.keys()) + list(new_weights.keys())))
    cost = capital * turnover * TRANSACTION_COST_BPS / 10_000
    return cost


def get_week_dates():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    return monday.strftime("%Y-%m-%d"), friday.strftime("%Y-%m-%d")


def safe_div(a, b, default=0.0):
    return a / b if b != 0 else default


def pct_fmt(value):
    return f"{value * 100:+.2f}%" if value is not None else "N/A"


def format_allocation(allocation):
    lines = []
    for ticker, weight in sorted(allocation.items(), key=lambda x: -x[1]):
        if weight > 0.001:
            lines.append(f"  {ticker}: {weight * 100:.1f}%")
    return "\n".join(lines)
