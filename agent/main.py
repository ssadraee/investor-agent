"""
Autonomous Investor Agent — Main Entry Point
Usage:
  python -m agent.main --phase scan_and_allocate
  python -m agent.main --phase evaluate
  python -m agent.main --phase learn_and_report
"""
import argparse
import logging
import json
import sys
from datetime import datetime

from agent import storage
from agent.scanner import scan_market, fetch_prices, compute_return_covariance
from agent.regime import classify_regime
from agent.allocator import build_allocation
from agent.evaluator import evaluate_week
from agent.learner import learn_and_update, get_current_weights
from agent.reporter import (
    generate_report, generate_scan_report, generate_evaluate_report,
    save_report, send_email
)
from agent.config import UNIVERSE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def phase_scan_and_allocate():
    """Monday: Scan market, classify regime, build allocation."""
    logger.info("=" * 60)
    logger.info("PHASE: SCAN AND ALLOCATE")
    logger.info("=" * 60)

    # 1. Initialize DB
    storage.init_db()

    # 2. Scan market
    market_state = scan_market()
    if market_state.get("error"):
        logger.error(f"Market scan failed: {market_state['error']}")
        logger.info("Using fallback: equal weight defensive allocation")
        market_state = {"signals": {"vix_current": 25, "spy_momentum_21d": 0},
                        "available_tickers": list(UNIVERSE.keys())[:5],
                        "expected_returns": {t: 0 for t in list(UNIVERSE.keys())[:5]},
                        "timestamp": datetime.now().isoformat()}

    week_id = storage.save_weekly_state("scan", market_state)
    logger.info(f"Week {week_id}: Market state saved")

    # 3. Classify regime
    weights, confidence = get_current_weights()
    regime, regime_conf, regime_scores = classify_regime(
        market_state, weights
    )
    logger.info(f"Regime: {regime} (confidence: {regime_conf:.2f})")

    # 4. Compute covariance and expected returns
    available = market_state.get("available_tickers", [])
    expected_returns = market_state.get("expected_returns", {})

    prices = fetch_prices(available)
    if not prices.empty:
        cov_matrix, _ = compute_return_covariance(prices, available)
    else:
        import pandas as pd
        import numpy as np
        cov_matrix = pd.DataFrame(np.eye(len(available)) * 0.04,
                                  index=available, columns=available)

    # 5. Build allocation
    allocation = build_allocation(expected_returns, cov_matrix, regime, weights)

    # 6. Save
    rationale = (f"Regime={regime} (conf={regime_conf:.2f}). "
                 f"VIX={market_state.get('signals', {}).get('vix_current', 'N/A')}. "
                 f"{len([k for k in allocation if k != 'CASH'])} assets allocated.")

    storage.save_portfolio(week_id, allocation, regime, rationale)
    storage.save_weekly_state("allocate", {
        "allocation": allocation,
        "regime": regime,
        "regime_confidence": regime_conf,
        "regime_scores": regime_scores,
        "rationale": rationale,
    })

    logger.info(f"Allocation saved for week {week_id}:")
    for t, w in sorted(allocation.items(), key=lambda x: -x[1]):
        logger.info(f"  {t}: {w*100:.1f}%")

    # 7. Send email report
    current_prices = {}
    if not prices.empty:
        for t in allocation:
            if t != "CASH" and t in prices.columns:
                current_prices[t] = float(prices[t].iloc[-1])

    scan_html = generate_scan_report(
        week_id, market_state, regime, regime_conf, allocation, current_prices
    )
    email_sent = send_email(
        week_id, scan_html,
        subject=f"Investor Agent — Week {week_id} Scan & Allocation"
    )
    if email_sent:
        logger.info("Scan & allocation email report sent successfully")
    else:
        logger.warning("Scan & allocation email not sent (check configuration)")

    return week_id


def phase_evaluate():
    """Friday: Evaluate weekly performance."""
    logger.info("=" * 60)
    logger.info("PHASE: EVALUATE")
    logger.info("=" * 60)

    storage.init_db()
    week_id = storage.get_current_week_id()

    if week_id == 0:
        logger.error("No active week found. Run scan_and_allocate first.")
        return

    metrics = evaluate_week(week_id)
    storage.save_performance(week_id, metrics)
    storage.save_weekly_state("evaluate", metrics)

    logger.info(f"Week {week_id} performance:")
    logger.info(f"  Return: {metrics.get('weekly_return', 0)*100:+.2f}%")
    logger.info(f"  SPY:    {metrics.get('benchmark_spy', 0)*100:+.2f}%")
    logger.info(f"  Sharpe: {metrics.get('sharpe', 0):.2f}")
    logger.info(f"  Value:  €{metrics.get('portfolio_value', 10000):,.2f}")

    # Send email report
    eval_html = generate_evaluate_report(week_id, metrics)
    email_sent = send_email(
        week_id, eval_html,
        subject=f"Investor Agent — Week {week_id} Evaluation"
    )
    if email_sent:
        logger.info("Evaluation email report sent successfully")
    else:
        logger.warning("Evaluation email not sent (check configuration)")

    return metrics


def phase_learn_and_report():
    """Sunday: Learn from week, generate report, email it."""
    logger.info("=" * 60)
    logger.info("PHASE: LEARN AND REPORT")
    logger.info("=" * 60)

    storage.init_db()
    week_id = storage.get_current_week_id()

    if week_id == 0:
        logger.error("No active week found.")
        return

    # Get week data
    scan_state = storage.get_weekly_state(week_id, "scan")
    alloc_state = storage.get_weekly_state(week_id, "allocate")
    eval_state = storage.get_weekly_state(week_id, "evaluate")

    if not scan_state or not alloc_state:
        logger.error("Missing scan or allocation data for this week")
        return

    market_state = scan_state["data"]
    alloc_data = alloc_state["data"]
    allocation = alloc_data.get("allocation", {})
    regime = alloc_data.get("regime", "transition")
    regime_confidence = alloc_data.get("regime_confidence", 0.5)
    regime_scores = alloc_data.get("regime_scores", {})

    # Get metrics (from evaluate phase or compute fresh)
    if eval_state:
        metrics = eval_state["data"]
    else:
        logger.warning("No evaluation data — running evaluation now")
        metrics = evaluate_week(week_id)
        storage.save_performance(week_id, metrics)

    # Learn
    learning_result = learn_and_update(week_id, market_state, metrics, regime_scores)
    storage.save_weekly_state("learn", learning_result)

    # Generate report
    html = generate_report(
        week_id, market_state, regime, regime_confidence,
        allocation, metrics, learning_result
    )

    # Save to GitHub Pages
    filepath = save_report(week_id, html)
    logger.info(f"Report saved to {filepath}")

    # Send email
    email_sent = send_email(week_id, html)
    if email_sent:
        logger.info("Email report sent successfully")
    else:
        logger.warning("Email not sent (check configuration)")

    logger.info(f"Week {week_id} complete.")
    return week_id


def main():
    parser = argparse.ArgumentParser(description="Autonomous Investor Agent")
    parser.add_argument("--phase", required=True,
                        choices=["scan_and_allocate", "evaluate", "learn_and_report", "full_cycle"],
                        help="Which phase to run")
    args = parser.parse_args()

    logger.info(f"Starting phase: {args.phase}")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")

    if args.phase == "scan_and_allocate":
        phase_scan_and_allocate()
    elif args.phase == "evaluate":
        phase_evaluate()
    elif args.phase == "learn_and_report":
        phase_learn_and_report()
    elif args.phase == "full_cycle":
        # Run all phases in sequence (useful for testing)
        phase_scan_and_allocate()
        phase_evaluate()
        phase_learn_and_report()

    logger.info("Done.")


if __name__ == "__main__":
    main()
