"""
Allocator — Risk-optimized portfolio construction.
Mean-variance optimization with regime-dependent constraints.
"""
import numpy as np
from scipy.optimize import minimize
import logging
from agent.config import (
    UNIVERSE, MAX_POSITION_WEIGHT, MIN_ASSETS, MIN_POSITION_WEIGHT,
    MAX_CASH_WEIGHT, RISK_FREE_RATE, ANNUALIZATION_FACTOR,
    REGIME_PARAMS, EQUITY_TICKERS, BOND_TICKERS, ALT_TICKERS
)

logger = logging.getLogger(__name__)


def build_allocation(expected_returns, cov_matrix, regime, signal_weights=None):
    """
    Optimize portfolio allocation given expected returns, covariance, and regime.
    Returns dict of ticker->weight, including optional CASH.
    """
    params = REGIME_PARAMS.get(regime, REGIME_PARAMS["transition"])
    risk_aversion = params["risk_aversion"]

    tickers = list(expected_returns.keys())
    tickers = [t for t in tickers if t in cov_matrix.index and t in cov_matrix.columns]

    if len(tickers) < MIN_ASSETS:
        logger.warning(f"Only {len(tickers)} tickers available, below minimum {MIN_ASSETS}")
        if len(tickers) == 0:
            return {"CASH": 1.0}

    n = len(tickers)
    mu = np.array([expected_returns[t] for t in tickers])
    try:
        sigma = cov_matrix.loc[tickers, tickers].values
        # Regularize covariance to ensure positive semi-definite
        sigma = sigma + np.eye(n) * 1e-6
    except Exception as e:
        logger.error(f"Covariance extraction failed: {e}")
        return _equal_weight(tickers, params)

    # Classify assets
    eq_idx = [i for i, t in enumerate(tickers) if t in EQUITY_TICKERS]
    bd_idx = [i for i, t in enumerate(tickers) if t in BOND_TICKERS]

    # --- Optimization ---
    def neg_utility(w):
        port_ret = w @ mu
        port_var = w @ sigma @ w
        return -(port_ret - 0.5 * risk_aversion * port_var)

    # Constraints
    constraints = []
    # Weights sum to <= 1 (remainder is cash)
    constraints.append({"type": "ineq", "fun": lambda w: 1.0 - np.sum(w)})
    # Minimum invested (1 - max_cash)
    constraints.append({"type": "ineq", "fun": lambda w: np.sum(w) - (1.0 - MAX_CASH_WEIGHT)})
    # Equity cap
    if len(eq_idx) > 0:
        constraints.append({
            "type": "ineq",
            "fun": lambda w, idx=eq_idx: params["equity_max"] - sum(w[i] for i in idx)
        })
    # Bond floor
    if len(bd_idx) > 0:
        constraints.append({
            "type": "ineq",
            "fun": lambda w, idx=bd_idx: sum(w[i] for i in idx) - params["bond_min"]
        })

    bounds = [(0.0, MAX_POSITION_WEIGHT) for _ in range(n)]

    # Initial guess: equal weight
    w0 = np.ones(n) / n * (1.0 - params["cash_target"])

    try:
        result = minimize(
            neg_utility, w0, method="SLSQP",
            bounds=bounds, constraints=constraints,
            options={"maxiter": 1000, "ftol": 1e-10}
        )
        if result.success:
            weights = result.x
        else:
            logger.warning(f"Optimization did not converge: {result.message}")
            weights = w0
    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        weights = w0

    # Post-process: remove tiny weights, enforce minimums
    weights = _post_process_weights(weights, tickers, params)

    allocation = {}
    for i, t in enumerate(tickers):
        if weights[i] >= MIN_POSITION_WEIGHT:
            allocation[t] = round(float(weights[i]), 4)

    cash = round(1.0 - sum(allocation.values()), 4)
    if cash > 0.005:
        allocation["CASH"] = cash

    # Verify minimum assets
    non_cash = {k: v for k, v in allocation.items() if k != "CASH"}
    if len(non_cash) < MIN_ASSETS and len(tickers) >= MIN_ASSETS:
        logger.warning("Below minimum assets, falling back to diversified allocation")
        return _diversified_fallback(tickers, params, mu, sigma)

    logger.info(f"Allocation: {len(non_cash)} assets, {cash*100:.1f}% cash, regime={regime}")
    return allocation


def _post_process_weights(weights, tickers, params):
    """Clean up weights: remove dust, enforce caps."""
    w = weights.copy()
    # Zero out tiny positions
    w[w < MIN_POSITION_WEIGHT] = 0
    # Re-enforce cap
    w = np.minimum(w, MAX_POSITION_WEIGHT)
    # Renormalize
    total = w.sum()
    if total > 0:
        target_invested = 1.0 - params["cash_target"]
        w = w / total * min(target_invested, total)
    return w


def _equal_weight(tickers, params):
    """Simple equal-weight fallback."""
    cash = params["cash_target"]
    invested = 1.0 - cash
    w = invested / len(tickers) if len(tickers) > 0 else 0
    allocation = {t: round(w, 4) for t in tickers}
    if cash > 0.005:
        allocation["CASH"] = round(cash, 4)
    return allocation


def _diversified_fallback(tickers, params, mu, sigma):
    """Diversified allocation when optimizer fails minimum asset constraint."""
    n = len(tickers)
    target_invested = 1.0 - params["cash_target"]

    # Risk parity approach: inverse volatility weighting
    vols = np.sqrt(np.diag(sigma))
    vols[vols == 0] = 1.0
    inv_vol = 1.0 / vols
    raw_weights = inv_vol / inv_vol.sum() * target_invested

    # Enforce caps
    raw_weights = np.minimum(raw_weights, MAX_POSITION_WEIGHT)
    raw_weights = raw_weights / raw_weights.sum() * target_invested

    allocation = {}
    for i, t in enumerate(tickers):
        if raw_weights[i] >= MIN_POSITION_WEIGHT:
            allocation[t] = round(float(raw_weights[i]), 4)

    cash = round(1.0 - sum(allocation.values()), 4)
    if cash > 0.005:
        allocation["CASH"] = cash

    return allocation


def compute_equal_weight_benchmark(tickers):
    """Equal weight across all available equity tickers."""
    eq_tickers = [t for t in tickers if t in EQUITY_TICKERS]
    if not eq_tickers:
        eq_tickers = tickers
    w = 1.0 / len(eq_tickers) if eq_tickers else 0
    return {t: w for t in eq_tickers}


def compute_risk_parity_benchmark(cov_matrix, tickers):
    """Inverse-volatility weighted (simple risk parity)."""
    available = [t for t in tickers if t in cov_matrix.index]
    if not available:
        return {}
    vols = np.sqrt(np.diag(cov_matrix.loc[available, available].values))
    vols[vols == 0] = 1.0
    inv_vol = 1.0 / vols
    weights = inv_vol / inv_vol.sum()
    return {t: round(float(w), 4) for t, w in zip(available, weights)}
