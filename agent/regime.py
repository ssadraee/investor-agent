"""
Regime Classifier — Classifies market into risk_on, risk_off, transition, or crisis
using multiple signal dimensions.
"""
import numpy as np
import logging
from agent.config import VIX_LOW, VIX_HIGH, VIX_CRISIS

logger = logging.getLogger(__name__)


def classify_regime(signals, signal_weights=None):
    """
    Classify current market regime.
    Returns: regime string, confidence score, component scores dict.
    """
    if signal_weights is None:
        signal_weights = {
            "volatility_regime": 0.25,
            "momentum": 0.20,
            "yield_curve": 0.15,
            "macro_trend": 0.15,
            "cross_asset_momentum": 0.15,
            "mean_reversion": 0.10,
        }

    scores = {}

    # --- Volatility regime score (-1 = crisis, +1 = calm) ---
    vix = signals.get("vix_current", 20.0)
    if vix >= VIX_CRISIS:
        scores["volatility_regime"] = -1.0
    elif vix >= VIX_HIGH:
        scores["volatility_regime"] = -0.5 - 0.5 * (vix - VIX_HIGH) / (VIX_CRISIS - VIX_HIGH)
    elif vix <= VIX_LOW:
        scores["volatility_regime"] = 0.8
    else:
        scores["volatility_regime"] = 0.5 * (VIX_HIGH - vix) / (VIX_HIGH - VIX_LOW)

    # VIX trend
    vix_ma = signals.get("vix_ma20", vix)
    if vix > vix_ma * 1.1:
        scores["volatility_regime"] -= 0.2
    elif vix < vix_ma * 0.9:
        scores["volatility_regime"] += 0.1

    scores["volatility_regime"] = np.clip(scores["volatility_regime"], -1, 1)

    # --- Momentum score ---
    mom_63 = signals.get("spy_momentum_63d", 0)
    mom_21 = signals.get("spy_momentum_21d", 0)
    breadth = signals.get("breadth_positive", 0.5)

    mom_score = 0.0
    if mom_63 > 0.05:
        mom_score += 0.4
    elif mom_63 < -0.05:
        mom_score -= 0.4
    if mom_21 > 0.02:
        mom_score += 0.3
    elif mom_21 < -0.02:
        mom_score -= 0.3
    mom_score += (breadth - 0.5) * 0.6
    scores["momentum"] = np.clip(mom_score, -1, 1)

    # --- Yield curve score ---
    spread = signals.get("yield_spread", 0)
    if spread < -0.5:
        scores["yield_curve"] = -0.8  # Inverted = recessionary
    elif spread < 0:
        scores["yield_curve"] = -0.3
    elif spread > 1.0:
        scores["yield_curve"] = 0.6
    else:
        scores["yield_curve"] = spread * 0.3
    scores["yield_curve"] = np.clip(scores["yield_curve"], -1, 1)

    # --- Macro trend (based on equity/bond relative performance) ---
    eq_ret = signals.get("equity_avg_return_5d", 0)
    bd_ret = signals.get("bond_avg_return_5d", 0)
    if eq_ret > 0.005 and eq_ret > bd_ret:
        scores["macro_trend"] = 0.5
    elif eq_ret < -0.005 and bd_ret > eq_ret:
        scores["macro_trend"] = -0.5
    else:
        scores["macro_trend"] = 0.0

    # --- Cross-asset momentum ---
    eq_bond_corr = signals.get("equity_bond_corr_21d", -0.3)
    vol_premium = signals.get("vol_risk_premium", 0)
    cross_score = 0.0
    if eq_bond_corr > 0.3:
        cross_score -= 0.3  # Positive correlation = risk-off environment
    elif eq_bond_corr < -0.2:
        cross_score += 0.2  # Normal negative = diversification works
    if vol_premium > 5:
        cross_score -= 0.2  # High fear premium
    elif vol_premium < -2:
        cross_score += 0.2  # Complacency (contrarian signal)
    scores["cross_asset_momentum"] = np.clip(cross_score, -1, 1)

    # --- Mean reversion ---
    eq_vol = signals.get("equity_volatility_21d", 0.15)
    if eq_vol > 0.25:
        scores["mean_reversion"] = 0.3  # High vol tends to revert
    elif eq_vol < 0.10:
        scores["mean_reversion"] = -0.2  # Low vol may spike
    else:
        scores["mean_reversion"] = 0.0

    # --- Weighted composite ---
    composite = 0.0
    for signal_name, weight in signal_weights.items():
        composite += scores.get(signal_name, 0) * weight

    # --- Regime classification ---
    if composite >= 0.3:
        regime = "risk_on"
    elif composite <= -0.5:
        regime = "crisis"
    elif composite <= -0.15:
        regime = "risk_off"
    else:
        regime = "transition"

    # Override: VIX spike overrides everything
    if vix >= VIX_CRISIS:
        regime = "crisis"
        logger.warning(f"VIX CRISIS OVERRIDE: VIX={vix:.1f}")

    confidence = min(abs(composite) * 2, 1.0)

    logger.info(f"Regime: {regime} (composite={composite:.3f}, confidence={confidence:.2f})")

    return regime, confidence, scores
