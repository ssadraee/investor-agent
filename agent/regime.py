"""
Regime Classifier — Classifies market into risk_on, risk_off, transition, or crisis
using multiple signal dimensions spanning US market signals, global equity breadth,
FX stress, credit conditions, geopolitical risk, leading indicators, and monetary policy.
"""
import numpy as np
import logging
from agent.config import VIX_LOW, VIX_HIGH, VIX_CRISIS

logger = logging.getLogger(__name__)


def classify_regime(market_state_or_signals, signal_weights=None):
    """
    Classify current market regime.

    Accepts either:
      - Full market_state dict (new): contains 'signals', 'regional_signals',
        'fx_signals', 'geopolitical_proxy_signals', 'external_sources', 'macro_global'
      - Bare signals dict (legacy): same behaviour as before

    Returns: regime string, confidence score, component scores dict.
    """
    # --- Unpack inputs (backward-compatible) ---
    if "signals" in market_state_or_signals:
        market_state = market_state_or_signals
        signals  = market_state.get("signals", {})
        regional = market_state.get("regional_signals", {})
        fx       = market_state.get("fx_signals", {})
        geo      = market_state.get("geopolitical_proxy_signals", {})
        external = market_state.get("external_sources", {})
        macro_gl = market_state.get("macro_global", {})
    else:
        signals  = market_state_or_signals
        regional = fx = geo = external = macro_gl = {}

    if signal_weights is None:
        signal_weights = {
            # Original 6 — scaled ×0.65 to make room for 6 new dimensions
            "volatility_regime":    0.162,
            "momentum":             0.130,
            "yield_curve":          0.098,
            "macro_trend":          0.098,
            "cross_asset_momentum": 0.098,
            "mean_reversion":       0.064,
            # New 6 — daily/weekly/monthly global data sources
            "global_breadth":       0.080,   # daily: equity breadth + OECD CLI
            "fx_stress":            0.070,   # daily: safe-haven demand + EM FX
            "credit_conditions":    0.070,   # daily: HY/EM spreads + EPU
            "geopolitical_risk":    0.050,   # weekly: GDELT + World Bank + ACLED
            "leading_indicators":   0.050,   # monthly: OECD CLI + IMF forecasts
            "global_monetary":      0.030,   # monthly: ECB rates + M3 + int'l yields
        }

    scores = {}

    # ==========================================================================
    # ORIGINAL 6 SIGNAL SCORES (unchanged logic)
    # ==========================================================================

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

    vix_ma = signals.get("vix_ma20", vix)
    if vix > vix_ma * 1.1:
        scores["volatility_regime"] -= 0.2
    elif vix < vix_ma * 0.9:
        scores["volatility_regime"] += 0.1
    scores["volatility_regime"] = np.clip(scores["volatility_regime"], -1, 1)

    # --- Momentum score ---
    mom_63  = signals.get("spy_momentum_63d", 0)
    mom_21  = signals.get("spy_momentum_21d", 0)
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
        scores["yield_curve"] = -0.8
    elif spread < 0:
        scores["yield_curve"] = -0.3
    elif spread > 1.0:
        scores["yield_curve"] = 0.6
    else:
        scores["yield_curve"] = spread * 0.3
    scores["yield_curve"] = np.clip(scores["yield_curve"], -1, 1)

    # --- Macro trend (equity vs bond relative performance) ---
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
    vol_premium  = signals.get("vol_risk_premium", 0)
    cross_score = 0.0
    if eq_bond_corr > 0.3:
        cross_score -= 0.3
    elif eq_bond_corr < -0.2:
        cross_score += 0.2
    if vol_premium > 5:
        cross_score -= 0.2
    elif vol_premium < -2:
        cross_score += 0.2
    scores["cross_asset_momentum"] = np.clip(cross_score, -1, 1)

    # --- Mean reversion ---
    eq_vol = signals.get("equity_volatility_21d", 0.15)
    if eq_vol > 0.25:
        scores["mean_reversion"] = 0.3
    elif eq_vol < 0.10:
        scores["mean_reversion"] = -0.2
    else:
        scores["mean_reversion"] = 0.0

    # ==========================================================================
    # NEW 6 SIGNAL SCORES — all default to 0.0 if source data is unavailable
    # ==========================================================================

    # --- global_breadth: % of world equity markets rising + OECD CLI ---
    gb_score = 0.0
    gb_val = regional.get("global_breadth_21d")
    if gb_val is not None:
        if gb_val > 0.70:
            gb_score = 0.8
        elif gb_val > 0.50:
            gb_score = 0.3
        elif gb_val > 0.30:
            gb_score = -0.3
        else:
            gb_score = -0.8

        # OECD CLI breadth nudge: fraction of countries with CLI > 100 (expanding)
        oecd = external.get("oecd_cli", {})
        if oecd:
            cli_vals = [v for v in oecd.values() if isinstance(v, dict) and v.get("cli") is not None]
            if cli_vals:
                frac_expanding = sum(1 for v in cli_vals if v["cli"] > 100) / len(cli_vals)
                if frac_expanding > 0.60:
                    gb_score += 0.15
                elif frac_expanding < 0.40:
                    gb_score -= 0.15
    scores["global_breadth"] = float(np.clip(gb_score, -1, 1))

    # --- fx_stress: safe-haven demand + EM FX pressure + USD strength ---
    # Inputs are 21-day momentum values (e.g. 0.03 = 3% move).
    # Scale factors chosen so a 5-6% move reaches ±1.
    fx_score = 0.0
    safe_haven  = fx.get("safe_haven_demand_21d")    # positive = JPY/CHF rising = risk-off
    em_fx_stress = fx.get("em_fx_stress_21d")         # positive = EM FX weakening = stress
    usd_strength = fx.get("usd_basket_strength_21d")  # positive = USD strong (often risk-off)
    if safe_haven is not None:
        fx_score -= 0.5 * safe_haven / 0.04   # normalise: 4% move → ±0.5
    if em_fx_stress is not None:
        fx_score -= 0.3 * em_fx_stress / 0.04
    if usd_strength is not None:
        fx_score -= 0.2 * usd_strength / 0.04
    if safe_haven is not None or em_fx_stress is not None or usd_strength is not None:
        scores["fx_stress"] = float(np.clip(fx_score, -1, 1))
    else:
        scores["fx_stress"] = 0.0

    # --- credit_conditions: HY/EM credit spreads + EPU ---
    composite_stress = geo.get("composite_financial_stress")
    if composite_stress is not None:
        cc_score = -2.0 * composite_stress + 1.0   # 0→+1, 0.5→0, 1→-1
        if geo.get("credit_stress_flag"):
            cc_score -= 0.15
        if geo.get("em_credit_stress_flag"):
            cc_score -= 0.10
        scores["credit_conditions"] = float(np.clip(cc_score, -1, 1))
    else:
        scores["credit_conditions"] = 0.0

    # --- geopolitical_risk: GDELT conflict intensity + World Bank + ACLED ---
    geo_score = 0.0
    gdelt = external.get("gdelt", {})
    summary = gdelt.get("_summary", {})
    tension = summary.get("global_tension_score")
    if tension is not None:
        # 1.0 (normal) → +0.2; 2.0 (double) → −0.3; 3.0 → −1.0
        geo_score = np.clip(1.0 - (tension - 1.0) * 1.3, -1.0, 0.2)

        # World Bank structural political instability overlay
        wb = external.get("world_bank", {})
        em_countries = ["CN", "BR", "IN", "MX", "ZA"]
        wb_stability = [
            wb[c]["political_stability"]["value"]
            for c in em_countries
            if c in wb and "political_stability" in wb.get(c, {})
        ]
        if wb_stability:
            avg_stability = np.mean(wb_stability)
            if avg_stability < -0.5:
                geo_score -= 0.10   # structurally fragile EM governance

        # ACLED event spike amplifier (optional — only if key is configured)
        acled = external.get("acled", {})
        if acled:
            # Flag if any region has a high event count (>100 events in 30 days)
            high_conflict = any(
                r.get("event_count", 0) > 100 for r in acled.values()
                if isinstance(r, dict)
            )
            if high_conflict:
                geo_score -= 0.15

        scores["geopolitical_risk"] = float(np.clip(geo_score, -1, 1))
    else:
        scores["geopolitical_risk"] = 0.0

    # --- leading_indicators: OECD CLI + IMF GDP growth forecasts ---
    li_score = 0.0
    li_components = 0

    oecd = external.get("oecd_cli", {})
    if oecd:
        cli_entries = [v for v in oecd.values() if isinstance(v, dict) and v.get("cli") is not None]
        if cli_entries:
            # CLI breadth: fraction of countries expanding (CLI > 100)
            frac_exp = sum(1 for v in cli_entries if v["cli"] > 100) / len(cli_entries)
            if frac_exp > 0.60:
                li_score += 0.4
            elif frac_exp < 0.40:
                li_score -= 0.4
            # CLI momentum: fraction with positive MoM change
            mom_entries = [v for v in cli_entries if v.get("cli_mom") is not None]
            if mom_entries:
                frac_rising = sum(1 for v in mom_entries if v["cli_mom"] > 0) / len(mom_entries)
                if frac_rising > 0.60:
                    li_score += 0.2
                elif frac_rising < 0.40:
                    li_score -= 0.2
            li_components += 1

    imf = external.get("imf", {})
    if imf:
        g5 = ["US", "DE", "JP", "CN", "GB"]
        gdp_forecasts = [
            imf[c]["gdp_growth_forecast"]["value"]
            for c in g5
            if c in imf and "gdp_growth_forecast" in imf.get(c, {})
        ]
        if gdp_forecasts:
            avg_gdp = np.mean(gdp_forecasts)
            if avg_gdp > 2.5:
                li_score += 0.2
            elif avg_gdp < 0:
                li_score -= 0.4
            elif avg_gdp < 1.0:
                li_score -= 0.2
            li_components += 1

    scores["leading_indicators"] = float(np.clip(li_score, -1, 1)) if li_components > 0 else 0.0

    # --- global_monetary: ECB rate direction + M3 growth + int'l yield trend ---
    gm_score = 0.0
    gm_components = 0

    ecb = external.get("ecb", {})
    if ecb:
        dfr = ecb.get("deposit_facility_rate")
        if dfr is not None:
            change = dfr.get("change", 0)
            if change < -0.001:
                gm_score += 0.3    # ECB cutting = easing
            elif change > 0.001:
                gm_score -= 0.3    # ECB hiking = tightening
            gm_components += 1
        m3 = ecb.get("m3_growth_yoy")
        if m3 is not None:
            m3_val = m3.get("latest", 0)
            if m3_val > 5.0:
                gm_score += 0.1    # broad money expanding
            elif m3_val < 0:
                gm_score -= 0.2    # money supply contracting

    # International yield direction (EA, Japan, UK 10Y from FRED global data)
    yield_keys = ["IRLTLT01EZM156N", "IRLTLT01JPM156N", "IRLTLT01GBM156N"]
    yield_changes = [
        macro_gl[k]["change"] for k in yield_keys
        if k in macro_gl and macro_gl[k].get("change") is not None
    ]
    if len(yield_changes) >= 2:
        if all(c > 0 for c in yield_changes):
            gm_score -= 0.15   # all rising = global tightening
        elif all(c < 0 for c in yield_changes):
            gm_score += 0.15   # all falling = global easing
        gm_components += 1

    scores["global_monetary"] = float(np.clip(gm_score, -1, 1)) if gm_components > 0 else 0.0

    # ==========================================================================
    # WEIGHTED COMPOSITE → REGIME CLASSIFICATION
    # ==========================================================================

    composite = sum(scores.get(name, 0) * weight for name, weight in signal_weights.items())

    if composite >= 0.3:
        regime = "risk_on"
    elif composite <= -0.5:
        regime = "crisis"
    elif composite <= -0.15:
        regime = "risk_off"
    else:
        regime = "transition"

    # VIX crisis override — hard gate regardless of other signals
    if vix >= VIX_CRISIS:
        regime = "crisis"
        logger.warning(f"VIX CRISIS OVERRIDE: VIX={vix:.1f}")

    confidence = min(abs(composite) * 2, 1.0)

    logger.info(
        f"Regime: {regime} (composite={composite:.3f}, confidence={confidence:.2f}) | "
        f"breadth={scores.get('global_breadth', 0):.2f} "
        f"fx={scores.get('fx_stress', 0):.2f} "
        f"credit={scores.get('credit_conditions', 0):.2f} "
        f"geo={scores.get('geopolitical_risk', 0):.2f} "
        f"lead={scores.get('leading_indicators', 0):.2f} "
        f"mon={scores.get('global_monetary', 0):.2f}"
    )

    return regime, confidence, scores
