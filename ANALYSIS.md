# Reverse-Engineering Analysis: $10,000 Allocation System

## 1. Codebase Overview

| File | Role |
|---|---|
| `agent/config.py` | Central parameter store — capital, universe, constraints, regime budgets, learning params |
| `agent/scanner.py` | Market data ingestion via yfinance + FRED; computes derived signals (VIX, momentum, yield curve, breadth, correlation) |
| `agent/regime.py` | Classifies market into 4 regimes (`risk_on`, `risk_off`, `transition`, `crisis`) via weighted composite score |
| `agent/allocator.py` | Mean-variance optimizer (scipy SLSQP) with regime-dependent constraints; produces `{ticker: weight}` |
| `agent/evaluator.py` | Weekly performance: weighted portfolio return, Sharpe, Sortino, max drawdown, 3 benchmarks |
| `agent/learner.py` | Bayesian confidence updates on 6 signals; constrained weight drift; error pattern detection |
| `agent/main.py` | Orchestrator — 3 phases: Mon (scan+allocate), Fri (evaluate), Sun (learn+report) |
| `agent/storage.py` | SQLite persistence for all weekly state |
| `agent/reporter.py` | HTML report generation + email |

**Data flow:** `scanner` → `regime` → `allocator` → `storage` → `evaluator` → `learner` → `reporter`

## 2. Model Identification

**Hybrid system** combining:

| Type | Where |
|---|---|
| **Rule-based** | `regime.py` — threshold-based signal scoring (VIX levels, momentum thresholds, yield spread cutoffs) |
| **Portfolio optimization** | `allocator.py` — mean-variance optimization via `scipy.optimize.minimize` (SLSQP) |
| **Heuristics** | `regime.py` — hardcoded score mappings; `allocator.py` — fallback to inverse-vol weighting |
| **Statistical model** | `scanner.py:178-193` — EWMA covariance estimation; momentum-based expected returns |
| **Bayesian learning** | `learner.py` — confidence-weighted signal updates with forgetting factor |

No ML model, no simulation, no backtesting loop.

## 3. Allocation Mechanism (Step-by-Step)

### Step 1 — Inputs (`scanner.py:scan_market`)
- 252 days of prices for 19 ETFs + VIX/treasury indices via `yfinance`
- FRED macro data (10Y/2Y yields, USD, unemployment, CPI, GDP, Fed Funds)

### Step 2 — Signal Computation (`scanner.py:compute_market_signals`)
- VIX level + 20-day MA + percentile
- SPY 63-day and 21-day momentum
- Equity/bond 5-day avg returns, 21-day correlation
- Market breadth (% of equity tickers with positive weekly return)
- Yield spread (^TNX - ^FVX)
- Vol risk premium (VIX - realized vol)

### Step 3 — Regime Classification (`regime.py:classify_regime`)
- 6 signals scored on [-1, +1] scale with hardcoded thresholds
- Weighted composite: `volatility_regime(0.25) + momentum(0.20) + yield_curve(0.15) + macro_trend(0.15) + cross_asset_momentum(0.15) + mean_reversion(0.10)`
- Composite ≥ 0.3 → `risk_on`; ≤ -0.5 → `crisis`; ≤ -0.15 → `risk_off`; else → `transition`
- Hard override: VIX ≥ 35 → `crisis` regardless

### Step 4 — Expected Returns (`scanner.py:213-218`)
- Annualized 63-day momentum: `(price_now / price_63d_ago - 1) / (63/252)`

### Step 5 — Covariance (`scanner.py:compute_return_covariance`)
- EWMA covariance with 21-day halflife, regularized with `+ I * 1e-6`

### Step 6 — Optimization (`allocator.py:build_allocation`)
- Objective: maximize `w·μ - 0.5 * risk_aversion * w·Σ·w` (mean-variance utility)
- `risk_aversion` is regime-dependent: 1.0 (risk_on) to 5.0 (crisis)
- Constraints:
  - Weights sum ≤ 1.0 (remainder = cash)
  - Minimum invested ≥ 70% (`1 - MAX_CASH_WEIGHT`)
  - Equity allocation ≤ regime max (30%–85%)
  - Bond allocation ≥ regime min (5%–30%)
  - Individual position ≤ 40%

### Step 7 — Post-Processing (`allocator.py:_post_process_weights`)
- Zero out positions < 2%
- Re-enforce 40% cap
- Renormalize to target invested amount
- If < 3 assets survive, fallback to inverse-volatility weighting

### Step 8 — Output
- `{ticker: weight, "CASH": remainder}` — weights sum to 1.0, applied to €10,000

## 4. Parameter Adjustment vs Structural Logic

### Adjustable Parameters (tuning knobs)

| Parameter | Value | File:Line |
|---|---|---|
| `INITIAL_CAPITAL` | 10,000 | `config.py:8` |
| `MAX_POSITION_WEIGHT` | 0.40 | `config.py:44` |
| `MIN_ASSETS` | 3 | `config.py:45` |
| `MAX_CASH_WEIGHT` | 0.30 | `config.py:46` |
| `RISK_FREE_RATE` | 0.045 | `config.py:50` |
| `EWMA_HALFLIFE` | 21 | `config.py:51` |
| `VIX_LOW/HIGH/CRISIS` | 16/25/35 | `config.py:56-58` |
| `REGIME_PARAMS` (4 regimes) | equity_max, bond_min, cash_target, risk_aversion | `config.py:62-87` |
| `LEARNING_RATE` | 0.1 | `config.py:95` |
| `FORGETTING_FACTOR` | 0.95 | `config.py:96` |
| `MAX_WEIGHT_DEVIATION` | 0.20 | `config.py:98` |
| Signal weights | 0.10–0.25 | `regime.py:18-25` |

### Hardcoded Rules (not configurable without code changes)

- Regime classification thresholds: 0.3, -0.15, -0.5 (`regime.py:117-124`)
- Signal score mappings (e.g., VIX ≥ 35 → -1.0, momentum > 5% → +0.4) (`regime.py:29-109`)
- Expected returns = annualized momentum only (`scanner.py:217-218`)
- VIX crisis override (`regime.py:127-129`)
- Confidence update asymmetry: +0.05 correct, -0.03 wrong (`learner.py:62-69`)

### Structural Logic (determines system behavior)

- **Mean-variance optimization** is the core allocator — changing it changes everything
- **Regime → risk_aversion mapping** is the primary behavioral switch
- **Signal → composite → regime** pipeline is the decision backbone
- **Weekly cadence** (Mon/Fri/Sun) constrains responsiveness

## 5. Current Improvement Mechanism

| Capability | Present? | Details |
|---|---|---|
| **Learns** | Yes (limited) | `learner.py` — Bayesian confidence on 6 signals |
| **Updates parameters** | Yes (constrained) | Signal weights drift ±20% from defaults after 8 weeks |
| **Retrains models** | No | No model retraining; only weight adjustments |
| **Logs feedback** | Yes | `storage.save_learning_log` — errors, improvements, pred_vs_actual |
| **Backtesting** | No | No historical simulation or strategy validation |

The learning is **conservative**: forgetting factor of 0.95 pulls confidence toward 0.5, max weight deviation is ±20%, and updates only begin after 8 weeks. The system cannot discover new signals, change regime thresholds, or modify the optimization approach.

## 6. True System Improvements (Code-Level)

### 6.1 Modular Scoring Engine
**Current:** Monolithic `classify_regime()` with hardcoded thresholds.
**Improvement:** Abstract each signal into a `Signal` class with `score(data) -> float` interface. Add a `SignalRegistry` to dynamically load/disable signals.
**Impact:** Enables A/B testing of signals, pluggable new indicators, per-signal backtesting.

### 6.2 Ensemble Decision Layer
**Current:** Single weighted-average composite → threshold-based regime.
**Improvement:** Replace with ensemble of classifiers (e.g., weighted vote, stacking). Each could use a different method (threshold, logistic regression, tree-based).
**Impact:** More robust regime classification, reduces sensitivity to any single signal failing.

### 6.3 Backtesting Loop
**Current:** No historical validation. The system only evaluates forward.
**Improvement:** Add a `backtester.py` module that replays historical data through `classify_regime` → `build_allocation` → `evaluate_week`. Compute out-of-sample Sharpe, turnover, and drawdown.
**Impact:** Enables parameter optimization, strategy validation before deployment, confidence in parameter changes.

### 6.4 Risk Model (Beyond Mean-Variance)
**Current:** Simple EWMA covariance → mean-variance utility.
**Improvement:** Add CVaR (Conditional Value-at-Risk) or Black-Litterman model. Incorporate drawdown constraints directly in the optimizer.
**Impact:** Better tail-risk management. Mean-variance is known to be sensitive to expected return estimates, which here are just momentum — a fragile input.

### 6.5 Reinforcement Feedback Pipeline
**Current:** Bayesian confidence updates compare signal direction to weekly return direction (binary correct/wrong).
**Improvement:** Track signal-to-return magnitude correlation, not just direction. Use online gradient descent on signal weights to minimize portfolio regret. Add a reward signal based on risk-adjusted returns (Sharpe) not raw returns.
**Impact:** Faster, more meaningful adaptation. Current binary feedback discards magnitude information.

### 6.6 Dynamic Universe Selection
**Current:** Fixed 19-ETF universe in `config.py`.
**Improvement:** Add a universe screening module that ranks ETFs by liquidity, momentum, and factor exposure, refreshing the investable set monthly.
**Impact:** Avoids stale allocations to underperforming sectors; adapts to market structure changes.

### 6.7 Transaction-Cost-Aware Optimization
**Current:** Transaction costs applied *after* optimization (`evaluator.py:76-77`).
**Improvement:** Include turnover penalty directly in the optimizer objective: `utility - λ * |w_new - w_old|`.
**Impact:** Reduces unnecessary rebalancing. Current system may churn positions weekly because the optimizer doesn't see the cost.
