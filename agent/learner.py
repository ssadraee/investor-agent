"""
Learning Engine — Bayesian signal weight updates, prediction tracking,
and self-improvement logic.
"""
import numpy as np
import logging
from agent.config import (
    SIGNALS, LEARNING_RATE, FORGETTING_FACTOR,
    MIN_WEEKS_BEFORE_DRIFT, MAX_WEIGHT_DEVIATION
)
from agent import storage

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {s: 1.0 / len(SIGNALS) for s in SIGNALS}
DEFAULT_CONFIDENCE = {s: 0.5 for s in SIGNALS}


def get_current_weights():
    """Load latest signal weights or return defaults."""
    saved = storage.get_latest_signal_weights()
    if saved:
        weights = saved["weights"]
        confidence = saved["confidence"]
        # Back-fill any signals added since weights were last persisted
        for s in SIGNALS:
            weights.setdefault(s, DEFAULT_WEIGHTS[s])
            confidence.setdefault(s, DEFAULT_CONFIDENCE[s])
        return weights, confidence
    return DEFAULT_WEIGHTS.copy(), DEFAULT_CONFIDENCE.copy()


def learn_and_update(week_id, market_state, metrics, regime_scores):
    """
    Main learning function. Compares predictions vs actuals,
    updates signal weights, logs improvements.
    """
    weights, confidence = get_current_weights()
    all_perf = storage.get_all_performance()
    n_weeks = len(all_perf)

    errors = []
    improvements = []
    pred_vs_actual = {}

    # --- 1. Compare predicted regime direction vs actual return ---
    predicted_direction = _regime_to_direction(market_state)
    actual_return = metrics.get("weekly_return", 0)
    actual_direction = "positive" if actual_return > 0 else "negative"

    direction_correct = predicted_direction == actual_direction
    pred_vs_actual["regime_direction"] = {
        "predicted": predicted_direction,
        "actual": actual_direction,
        "correct": direction_correct,
    }

    if not direction_correct:
        errors.append(f"Regime predicted {predicted_direction} but return was {actual_direction} ({actual_return:.4f})")

    # --- 2. Evaluate each signal's contribution ---
    for signal_name in SIGNALS:
        score = regime_scores.get(signal_name, 0)
        signal_predicted_up = score > 0

        if signal_predicted_up == (actual_return > 0):
            # Signal was correct — increase confidence, maintain weight
            confidence[signal_name] = min(
                confidence[signal_name] + LEARNING_RATE * 0.5, 1.0
            )
            improvements.append(f"{signal_name}: correct (score={score:.3f}), confidence up")
        else:
            # Signal was wrong — decrease confidence
            confidence[signal_name] = max(
                confidence[signal_name] - LEARNING_RATE * 0.3, 0.1
            )
            errors.append(f"{signal_name}: wrong (score={score:.3f} vs return={actual_return:.4f})")

        pred_vs_actual[signal_name] = {
            "score": round(score, 4),
            "predicted_up": signal_predicted_up,
            "actual_up": actual_return > 0,
            "correct": signal_predicted_up == (actual_return > 0),
        }

    # --- 3. Update weights based on confidence ---
    if n_weeks >= MIN_WEEKS_BEFORE_DRIFT:
        new_weights = _update_weights(weights, confidence)
        improvements.append(f"Weights updated after {n_weeks} weeks of data")
    else:
        new_weights = weights.copy()
        improvements.append(f"Weights held (need {MIN_WEEKS_BEFORE_DRIFT - n_weeks} more weeks)")

    # --- 4. Apply forgetting factor ---
    for s in SIGNALS:
        confidence[s] = confidence[s] * FORGETTING_FACTOR + (1 - FORGETTING_FACTOR) * 0.5

    # --- 5. Detect specific error patterns ---
    pattern_errors = _detect_error_patterns(all_perf, metrics)
    errors.extend(pattern_errors)

    # --- 6. Benchmark comparison insights ---
    spy_ret = metrics.get("benchmark_spy", 0)
    port_ret = metrics.get("weekly_return", 0)
    if spy_ret != 0 and port_ret < spy_ret:
        gap = spy_ret - port_ret
        if gap > 0.01:
            errors.append(f"Underperformed SPY by {gap*100:.2f}% — review allocation aggressiveness")
        improvements.append("Consider increasing equity weight if momentum is strong")
    elif port_ret > spy_ret:
        improvements.append(f"Outperformed SPY by {(port_ret - spy_ret)*100:.2f}%")

    # --- 7. Risk model check ---
    expected_vol = market_state.get("signals", {}).get("equity_volatility_21d", 0.15)
    realized_vol = metrics.get("volatility", 0)
    if realized_vol > 0 and expected_vol > 0:
        vol_ratio = realized_vol / expected_vol
        pred_vs_actual["volatility"] = {
            "expected": round(expected_vol, 4),
            "realized": round(realized_vol, 4),
            "ratio": round(vol_ratio, 4),
        }
        if vol_ratio > 1.5:
            errors.append(f"Realized vol {realized_vol:.2f} >> expected {expected_vol:.2f}")
        elif vol_ratio < 0.5:
            improvements.append("Risk model overestimated volatility — can take more risk")

    # Save
    storage.save_signal_weights(week_id, new_weights, confidence)
    storage.save_learning_log(week_id, errors, improvements, pred_vs_actual)

    logger.info(f"Learning complete: {len(errors)} errors, {len(improvements)} improvements")

    return {
        "weights": new_weights,
        "confidence": confidence,
        "errors": errors,
        "improvements": improvements,
        "pred_vs_actual": pred_vs_actual,
    }


def _regime_to_direction(market_state):
    """Infer predicted direction from market state."""
    signals = market_state.get("signals", {})
    mom = signals.get("spy_momentum_21d", 0)
    return "positive" if mom > 0 else "negative"


def _update_weights(weights, confidence):
    """Update weights proportional to confidence, constrained by max deviation."""
    new_weights = {}
    total_conf = sum(confidence.values())
    if total_conf == 0:
        return DEFAULT_WEIGHTS.copy()

    for s in SIGNALS:
        target = confidence[s] / total_conf
        current = weights.get(s, DEFAULT_WEIGHTS[s])
        default = DEFAULT_WEIGHTS[s]

        # Constrain deviation from default
        target = np.clip(target, default - MAX_WEIGHT_DEVIATION, default + MAX_WEIGHT_DEVIATION)
        # Smooth update
        new_weights[s] = current * FORGETTING_FACTOR + target * (1 - FORGETTING_FACTOR)

    # Normalize
    total = sum(new_weights.values())
    if total > 0:
        new_weights = {k: round(v / total, 6) for k, v in new_weights.items()}

    return new_weights


def _detect_error_patterns(all_perf, current_metrics):
    """Look for systematic error patterns across history."""
    errors = []
    if len(all_perf) < 4:
        return errors

    recent = all_perf[-4:]
    recent_returns = [p.get("weekly_return", 0) for p in recent if p.get("weekly_return") is not None]

    # Consecutive losses
    if len(recent_returns) >= 3 and all(r < 0 for r in recent_returns[-3:]):
        errors.append("3+ consecutive losing weeks — consider defensive shift")

    # Increasing drawdown
    recent_dd = [p.get("max_drawdown", 0) for p in recent if p.get("max_drawdown") is not None]
    if len(recent_dd) >= 2 and recent_dd[-1] < recent_dd[-2] - 0.02:
        errors.append("Drawdown deepening — risk model may be too aggressive")

    # Persistent underperformance vs SPY
    spy_wins = sum(1 for p in all_perf[-4:]
                   if p.get("benchmark_spy") is not None and p.get("weekly_return") is not None
                   and p["weekly_return"] < p["benchmark_spy"])
    if spy_wins >= 3:
        errors.append("Underperformed SPY 3 of last 4 weeks — review factor exposure")

    return errors
