"""
Reporter — Generates HTML weekly reports for GitHub Pages and sends email.
"""
import os
import json
import smtplib
import logging
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

import math

from agent.config import (
    EMAIL_RECIPIENT, EMAIL_SENDER, EMAIL_APP_PASSWORD,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    DOCS_PATH, HISTORY_PATH, INITIAL_CAPITAL, UNIVERSE
)
from agent import storage
from agent.utils import pct_fmt

logger = logging.getLogger(__name__)


def _nf(value, decimals=1):
    """Safe number format. Returns formatted string or 'N/A'."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimals}f}"
    except (ValueError, TypeError):
        return str(value)


def _npct(value):
    """Safe percent format from decimal (0.05 -> '5%')."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value) * 100:.0f}%"
    except (ValueError, TypeError):
        return str(value)


def _safe_float(value, default=0.0):
    """Safely convert to float."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def generate_report(week_id, market_state, regime, regime_confidence,
                    allocation, metrics, learning_result):
    """Generate full HTML report. Returns HTML string."""
    signals = market_state.get("signals", {})
    macro = market_state.get("macro", {})

    vix_current = _nf(signals.get("vix_current"), 1)
    vix_ma20 = _nf(signals.get("vix_ma20"), 1)
    spy_mom_21 = pct_fmt(signals.get("spy_momentum_21d"))
    spy_mom_63 = pct_fmt(signals.get("spy_momentum_63d"))
    yield_spread = _nf(signals.get("yield_spread", 0), 2)
    breadth = _npct(signals.get("breadth_positive", 0))
    eq_bond_corr = _nf(signals.get("equity_bond_corr_21d", 0), 3)
    vol_premium = _nf(signals.get("vol_risk_premium", 0), 2)
    conf_pct = _npct(regime_confidence)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Week {week_id} Report — Autonomous Investor Agent</title>
<style>
:root {{ --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9;
  --accent: #58a6ff; --green: #3fb950; --red: #f85149; --yellow: #d29922; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg); color: var(--text); padding: 20px; max-width: 900px; margin: 0 auto; }}
h1 {{ color: var(--accent); margin-bottom: 8px; font-size: 1.5em; }}
h2 {{ color: var(--accent); margin: 24px 0 12px; font-size: 1.15em; border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
.subtitle {{ color: #8b949e; margin-bottom: 20px; }}
.card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  padding: 16px; margin-bottom: 16px; }}
.metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
.metric {{ text-align: center; padding: 12px; }}
.metric .value {{ font-size: 1.5em; font-weight: 700; }}
.metric .label {{ font-size: 0.85em; color: #8b949e; margin-top: 4px; }}
.positive {{ color: var(--green); }}
.negative {{ color: var(--red); }}
.neutral {{ color: var(--yellow); }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
th {{ color: var(--accent); font-weight: 600; }}
.regime-badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-weight: 600; font-size: 0.9em; }}
.regime-risk_on {{ background: #1a3a1a; color: var(--green); }}
.regime-risk_off {{ background: #3a1a1a; color: var(--red); }}
.regime-transition {{ background: #3a3a1a; color: var(--yellow); }}
.regime-crisis {{ background: #3a0a0a; color: #ff6b6b; }}
ul {{ margin: 8px 0 8px 20px; }}
li {{ margin: 4px 0; }}
.disclaimer {{ margin-top: 30px; padding: 12px; font-size: 0.8em; color: #8b949e; border-top: 1px solid var(--border); }}
</style>
</head>
<body>
<h1>Week {week_id} Report</h1>
<p class="subtitle">Generated {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} — Autonomous Investor Agent</p>

<h2>1. Market Regime</h2>
<div class="card">
  <p>Regime: <span class="regime-badge regime-{regime}">{regime.upper().replace('_', ' ')}</span>
     &nbsp; Confidence: {conf_pct}</p>
  <p style="margin-top:8px">VIX: {vix_current} &nbsp;|&nbsp;
     SPY Momentum (21d): {spy_mom_21} &nbsp;|&nbsp;
     Yield Spread: {yield_spread} &nbsp;|&nbsp;
     Breadth: {breadth}</p>
</div>

<h2>2. Signals Summary</h2>
<div class="card">
  <table>
    <tr><th>Signal</th><th>Value</th></tr>
    <tr><td>VIX Current</td><td>{vix_current}</td></tr>
    <tr><td>VIX 20-day MA</td><td>{vix_ma20}</td></tr>
    <tr><td>SPY Momentum 63d</td><td>{spy_mom_63}</td></tr>
    <tr><td>SPY Momentum 21d</td><td>{spy_mom_21}</td></tr>
    <tr><td>Equity-Bond Correlation</td><td>{eq_bond_corr}</td></tr>
    <tr><td>Vol Risk Premium</td><td>{vol_premium}</td></tr>
    <tr><td>Market Breadth</td><td>{breadth} positive</td></tr>
  </table>
</div>

{_macro_section(macro)}

<h2>3. Portfolio Allocation</h2>
<div class="card">
  <table>
    <tr><th>Asset</th><th>Weight</th><th>EUR Value</th></tr>
    {_allocation_rows(allocation, metrics.get('portfolio_value', INITIAL_CAPITAL))}
  </table>
</div>

<h2>4. Expected vs Realized Risk/Return</h2>
<div class="card metric-grid">
  {_metric_card("Weekly Return", metrics.get('weekly_return', 0), True)}
  {_metric_card("Cumulative Return", metrics.get('cumulative_return', 0), True)}
  {_metric_card("Portfolio Value", metrics.get('portfolio_value', INITIAL_CAPITAL), False, prefix="EUR ")}
  {_metric_card("Sharpe Ratio", metrics.get('sharpe', 0), True, is_pct=False)}
  {_metric_card("Sortino Ratio", metrics.get('sortino', 0), True, is_pct=False)}
  {_metric_card("Max Drawdown", metrics.get('max_drawdown', 0), True)}
  {_metric_card("Annualized Vol", metrics.get('volatility', 0), False)}
  {_metric_card("Transaction Cost", metrics.get('transaction_cost', 0), False, prefix="EUR ")}
</div>

<h2>5. Benchmark Comparison</h2>
<div class="card">
  <table>
    <tr><th>Strategy</th><th>Weekly Return</th><th>vs Agent</th></tr>
    {_benchmark_rows(metrics)}
  </table>
</div>

<h2>6. Errors Identified</h2>
<div class="card">
  {_list_section(learning_result.get('errors', []), 'No errors detected this week.')}
</div>

<h2>7. Model Updates</h2>
<div class="card">
  {_list_section(learning_result.get('improvements', []), 'No updates this week.')}
</div>

<h2>8. Signal Weights</h2>
<div class="card">
  <table>
    <tr><th>Signal</th><th>Weight</th><th>Confidence</th></tr>
    {_weights_rows(learning_result.get('weights', {}), learning_result.get('confidence', {}))}
  </table>
</div>

<h2>9. Forward Adjustment</h2>
<div class="card">
  <p>{_forward_note(learning_result, metrics, regime)}</p>
</div>

{_equity_curve_section()}

<div class="disclaimer">
  <strong>DISCLAIMER:</strong> This is a virtual portfolio simulation for educational purposes only.
  No real money is at risk. Not financial advice. Past simulated performance does not indicate future results.
</div>
</body>
</html>"""

    return html


def _base_css():
    """Shared CSS for all email reports."""
    return """:root { --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9;
  --accent: #58a6ff; --green: #3fb950; --red: #f85149; --yellow: #d29922; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg); color: var(--text); padding: 20px; max-width: 900px; margin: 0 auto; }
h1 { color: var(--accent); margin-bottom: 8px; font-size: 1.5em; }
h2 { color: var(--accent); margin: 24px 0 12px; font-size: 1.15em; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
.subtitle { color: #8b949e; margin-bottom: 20px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  padding: 16px; margin-bottom: 16px; }
.positive { color: var(--green); }
.negative { color: var(--red); }
.neutral { color: var(--yellow); }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }
th { color: var(--accent); font-weight: 600; }
.regime-badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-weight: 600; font-size: 0.9em; }
.regime-risk_on { background: #1a3a1a; color: var(--green); }
.regime-risk_off { background: #3a1a1a; color: var(--red); }
.regime-transition { background: #3a3a1a; color: var(--yellow); }
.regime-crisis { background: #3a0a0a; color: #ff6b6b; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.metric { text-align: center; padding: 12px; }
.metric .value { font-size: 1.5em; font-weight: 700; }
.metric .label { font-size: 0.85em; color: #8b949e; margin-top: 4px; }
ul { margin: 8px 0 8px 20px; }
li { margin: 4px 0; }
.disclaimer { margin-top: 30px; padding: 12px; font-size: 0.8em; color: #8b949e; border-top: 1px solid var(--border); }"""


_REGIME_LABELS = {
    "risk_on": "Confident Market",
    "risk_off": "Cautious Market",
    "transition": "Mixed Signals",
    "crisis": "Emergency Mode",
}


def generate_scan_report(week_id, market_state, regime, regime_confidence,
                         allocation, current_prices):
    """Generate a simple HTML email report for the Monday Scan & Allocate phase."""
    signals = market_state.get("signals", {})
    data_quality = market_state.get("data_quality", {})
    regime_label = _REGIME_LABELS.get(regime, regime)
    conf_pct = _npct(regime_confidence)

    # Compute portfolio value from historical performance
    all_perf = storage.get_all_performance()
    if all_perf:
        last = all_perf[-1]
        portfolio_value = _safe_float(last.get("portfolio_value"), INITIAL_CAPITAL)
    else:
        portfolio_value = INITIAL_CAPITAL

    # VIX interpretation
    vix = _safe_float(signals.get("vix_current"), 20)
    if vix < 16:
        vix_desc = "low (calm market)"
    elif vix < 25:
        vix_desc = "moderate"
    elif vix < 35:
        vix_desc = "elevated (nervous market)"
    else:
        vix_desc = "very high (fearful market)"

    # Momentum interpretation
    spy_mom = _safe_float(signals.get("spy_momentum_21d"), 0)
    if spy_mom > 0.02:
        mom_desc = "upward"
    elif spy_mom < -0.02:
        mom_desc = "downward"
    else:
        mom_desc = "sideways"

    # Allocation rows with shares
    alloc_rows = ""
    for ticker, weight in sorted(allocation.items(), key=lambda x: -_safe_float(x[1])):
        w = _safe_float(weight)
        eur_value = portfolio_value * w
        name = UNIVERSE.get(ticker, ticker)
        price = _safe_float(current_prices.get(ticker), 0)
        if ticker == "CASH" or price == 0:
            shares_str = "—"
            price_str = "—"
        else:
            shares = math.floor(eur_value / price)
            shares_str = str(shares)
            price_str = f"${price:,.2f}"
        alloc_rows += (f'<tr><td>{ticker}</td><td>{name}</td>'
                       f'<td>{w*100:.1f}%</td><td>EUR {eur_value:,.0f}</td>'
                       f'<td>{shares_str}</td><td>{price_str}</td></tr>')

    tickers_scanned = data_quality.get("tickers_fetched", len(allocation))
    days_data = data_quality.get("days_of_data", "N/A")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Week {week_id} — Scan & Allocation</title>
<style>{_base_css()}</style>
</head>
<body>
<h1>Week {week_id} — Scan & Allocation Report</h1>
<p class="subtitle">Generated {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} — Autonomous Investor Agent</p>

<h2>Market Overview</h2>
<div class="card">
  <p>The system assessed the current market and determined it is in
     <span class="regime-badge regime-{regime}">{regime_label}</span> mode
     (confidence: {conf_pct}).</p>
  <p style="margin-top:8px">Fear index (VIX): <strong>{_nf(vix, 1)}</strong> — {vix_desc}.</p>
  <p>Market trend over the past 21 days: <strong>{mom_desc}</strong>.</p>
</div>

<h2>Scan Results</h2>
<div class="card">
  <p>The system scanned <strong>{tickers_scanned}</strong> investment funds using
     <strong>{days_data}</strong> days of price history.</p>
  <p>It looked at market fear levels, price trends, bond vs stock behavior,
     and sector health to decide how to invest.</p>
</div>

<h2>Allocation Summary</h2>
<div class="card">
  <p style="margin-bottom:12px">Based on the "{regime_label}" assessment, the system
     allocated <strong>EUR {portfolio_value:,.0f}</strong> as follows:</p>
  <table>
    <tr><th>Fund</th><th>Name</th><th>Weight</th><th>EUR Value</th><th>Shares</th><th>Price</th></tr>
    {alloc_rows}
  </table>
  <p style="margin-top:12px; font-size:0.85em; color:#8b949e">
    Shares are approximate (rounded down). Actual execution may vary slightly.</p>
</div>

<div class="disclaimer">
  <strong>DISCLAIMER:</strong> This is a virtual portfolio simulation for educational purposes only.
  No real money is at risk. Not financial advice.
</div>
</body>
</html>"""

    return html


def generate_evaluate_report(week_id, metrics):
    """Generate a simple HTML email report for the Friday Evaluate phase."""
    weekly_ret = _safe_float(metrics.get("weekly_return"))
    cum_ret = _safe_float(metrics.get("cumulative_return"))
    port_value = _safe_float(metrics.get("portfolio_value"), INITIAL_CAPITAL)
    sharpe = _safe_float(metrics.get("sharpe"))
    sortino = _safe_float(metrics.get("sortino"))
    max_dd = _safe_float(metrics.get("max_drawdown"))
    vol = _safe_float(metrics.get("volatility"))
    spy_ret = _safe_float(metrics.get("benchmark_spy"))
    ew_ret = _safe_float(metrics.get("benchmark_ew"))
    rp_ret = _safe_float(metrics.get("benchmark_rp"))

    # Plain-language findings
    findings = []

    # Weekly return
    if weekly_ret > 0:
        findings.append(f"The portfolio gained {pct_fmt(weekly_ret)} this week.")
    elif weekly_ret < 0:
        findings.append(f"The portfolio lost {pct_fmt(weekly_ret)} this week.")
    else:
        findings.append("The portfolio was flat this week (no gain or loss).")

    # SPY comparison
    diff = weekly_ret - spy_ret
    if diff > 0.001:
        findings.append(f"We outperformed the S&P 500 by {pct_fmt(diff)}.")
    elif diff < -0.001:
        findings.append(f"We underperformed the S&P 500 by {pct_fmt(abs(diff))}.")
    else:
        findings.append("Performance was roughly in line with the S&P 500.")

    # Sharpe interpretation
    if sharpe > 1.5:
        findings.append(f"Risk-adjusted return score (Sharpe ratio) is strong at {sharpe:.2f}.")
    elif sharpe > 0.5:
        findings.append(f"Risk-adjusted return score (Sharpe ratio) is acceptable at {sharpe:.2f}.")
    elif sharpe > 0:
        findings.append(f"Risk-adjusted return score (Sharpe ratio) is low at {sharpe:.2f}.")
    else:
        findings.append(f"Risk-adjusted return score (Sharpe ratio) is negative at {sharpe:.2f} — returns are not compensating for risk taken.")

    # Drawdown
    if max_dd < -0.10:
        findings.append(f"Maximum drawdown has reached {pct_fmt(max_dd)} — this is a notable decline from peak value.")
    elif max_dd < -0.05:
        findings.append(f"Maximum drawdown is {pct_fmt(max_dd)} — moderate decline from peak.")

    findings_html = "<ul>" + "".join(f"<li>{f}</li>" for f in findings) + "</ul>"

    # Benchmark rows
    bench_rows = f"""
    <tr><td>Our Portfolio</td><td class="{_color_class(weekly_ret)}">{pct_fmt(weekly_ret)}</td></tr>
    <tr><td>S&P 500 (SPY)</td><td class="{_color_class(spy_ret)}">{pct_fmt(spy_ret)}</td></tr>
    <tr><td>Equal Weight</td><td class="{_color_class(ew_ret)}">{pct_fmt(ew_ret)}</td></tr>
    <tr><td>Risk Parity</td><td class="{_color_class(rp_ret)}">{pct_fmt(rp_ret)}</td></tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Week {week_id} — Evaluation</title>
<style>{_base_css()}</style>
</head>
<body>
<h1>Week {week_id} — Evaluation Report</h1>
<p class="subtitle">Generated {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} — Autonomous Investor Agent</p>

<h2>Performance Summary</h2>
<div class="card metric-grid">
  {_metric_card("Weekly Return", weekly_ret, True)}
  {_metric_card("Total Return", cum_ret, True)}
  {_metric_card("Portfolio Value", port_value, False, prefix="EUR ")}
</div>

<h2>Key Findings</h2>
<div class="card">
  {findings_html}
</div>

<h2>Benchmark Comparison</h2>
<div class="card">
  <p style="margin-bottom:8px">How our portfolio performed compared to common strategies this week:</p>
  <table>
    <tr><th>Strategy</th><th>Weekly Return</th></tr>
    {bench_rows}
  </table>
</div>

<div class="disclaimer">
  <strong>DISCLAIMER:</strong> This is a virtual portfolio simulation for educational purposes only.
  No real money is at risk. Not financial advice.
</div>
</body>
</html>"""

    return html


def save_report(week_id, html):
    """Save report to docs/ for GitHub Pages."""
    os.makedirs(HISTORY_PATH, exist_ok=True)

    filepath = os.path.join(HISTORY_PATH, f"week-{week_id}.html")
    with open(filepath, "w") as f:
        f.write(html)

    index_path = os.path.join(DOCS_PATH, "index.html")
    with open(index_path, "w") as f:
        f.write(html)

    _update_history_index()
    logger.info(f"Report saved: {filepath}")
    return filepath


def send_email(week_id, html, subject=None):
    """Send report via email. Subject defaults to the weekly report title."""
    if not EMAIL_SENDER or not EMAIL_APP_PASSWORD or not EMAIL_RECIPIENT:
        logger.warning("Email not configured — skipping email send")
        return False

    if subject is None:
        subject = f"Investor Agent — Week {week_id} Report"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECIPIENT

        text_part = MIMEText(f"Week {week_id} report attached. View online at your GitHub Pages URL.", "plain")
        html_part = MIMEText(html, "html")
        msg.attach(text_part)
        msg.attach(html_part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())

        logger.info(f"Email sent to {EMAIL_RECIPIENT}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


def send_telegram(text):
    """Send an HTML-formatted message to a Telegram chat via Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — skipping Telegram notification")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        logger.info("Telegram notification sent")
        return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


def notify_telegram_scan(week_id, regime, regime_conf, allocation):
    """Send a Telegram summary for the Monday scan & allocation phase."""
    regime_label = _REGIME_LABELS.get(regime, regime)
    conf_pct = int(_safe_float(regime_conf) * 100)

    all_perf = storage.get_all_performance()
    portfolio_value = _safe_float(all_perf[-1].get("portfolio_value"), INITIAL_CAPITAL) if all_perf else INITIAL_CAPITAL

    top_alloc = sorted(allocation.items(), key=lambda x: -_safe_float(x[1]))[:5]
    alloc_lines = ""
    for ticker, weight in top_alloc:
        w = _safe_float(weight)
        name = UNIVERSE.get(ticker, ticker)
        eur = portfolio_value * w
        alloc_lines += f"  {ticker} ({name}): <b>{w*100:.1f}%</b> — EUR {eur:,.0f}\n"

    text = (
        f"<b>Week {week_id} — Scan &amp; Allocation</b>\n\n"
        f"Regime: <b>{regime_label}</b> ({conf_pct}% confidence)\n\n"
        f"<b>Top Allocations</b>\n{alloc_lines}\n"
        f"Portfolio value: EUR {portfolio_value:,.0f}"
    )
    return send_telegram(text)


def notify_telegram_eval(week_id, metrics):
    """Send a Telegram summary for the Friday evaluation phase."""
    weekly_ret = _safe_float(metrics.get("weekly_return"))
    cum_ret = _safe_float(metrics.get("cumulative_return"))
    port_value = _safe_float(metrics.get("portfolio_value"), INITIAL_CAPITAL)
    sharpe = _safe_float(metrics.get("sharpe"))
    spy_ret = _safe_float(metrics.get("benchmark_spy"))
    diff = weekly_ret - spy_ret

    sign = "+" if weekly_ret >= 0 else ""
    spy_sign = "+" if diff >= 0 else ""

    text = (
        f"<b>Week {week_id} — Evaluation</b>\n\n"
        f"Weekly return: <b>{sign}{weekly_ret*100:.2f}%</b>\n"
        f"vs S&amp;P 500: <b>{spy_sign}{diff*100:.2f}%</b>\n"
        f"Cumulative return: <b>{cum_ret*100:.2f}%</b>\n"
        f"Portfolio value: <b>EUR {port_value:,.0f}</b>\n"
        f"Sharpe ratio: <b>{sharpe:.2f}</b>"
    )
    return send_telegram(text)


def notify_telegram_report(week_id, regime, regime_conf, metrics, learning_result):
    """Send a Telegram summary for the Sunday full report phase."""
    regime_label = _REGIME_LABELS.get(regime, regime)
    conf_pct = int(_safe_float(regime_conf) * 100)

    weekly_ret = _safe_float(metrics.get("weekly_return"))
    cum_ret = _safe_float(metrics.get("cumulative_return"))
    port_value = _safe_float(metrics.get("portfolio_value"), INITIAL_CAPITAL)
    sharpe = _safe_float(metrics.get("sharpe"))
    max_dd = _safe_float(metrics.get("max_drawdown"))
    spy_ret = _safe_float(metrics.get("benchmark_spy"))
    diff = weekly_ret - spy_ret

    sign = "+" if weekly_ret >= 0 else ""
    spy_sign = "+" if diff >= 0 else ""

    updates = learning_result.get("improvements", [])
    updates_text = ""
    if updates:
        updates_text = "\n<b>Model Updates</b>\n" + "".join(f"  • {u}\n" for u in updates[:3])

    text = (
        f"<b>Week {week_id} — Full Report</b>\n\n"
        f"Regime: <b>{regime_label}</b> ({conf_pct}% confidence)\n\n"
        f"<b>Performance</b>\n"
        f"  Weekly: <b>{sign}{weekly_ret*100:.2f}%</b> ({spy_sign}{diff*100:.2f}% vs SPY)\n"
        f"  Cumulative: <b>{cum_ret*100:.2f}%</b>\n"
        f"  Portfolio value: <b>EUR {port_value:,.0f}</b>\n"
        f"  Sharpe: <b>{sharpe:.2f}</b>  |  Max drawdown: <b>{max_dd*100:.2f}%</b>"
        f"{updates_text}"
    )
    return send_telegram(text)


# === HELPER FUNCTIONS ===

def _macro_section(macro):
    if not macro:
        return '<h2>Macro Data</h2><div class="card"><p>FRED data unavailable (no API key or fetch failed)</p></div>'
    rows = ""
    for key, data in macro.items():
        latest = _nf(data.get("latest"), 2)
        change = _nf(data.get("change", 0), 3)
        rows += f'<tr><td>{data.get("name", key)}</td><td>{latest}</td><td>{change}</td></tr>'
    return f'''<h2>Macro Data (FRED)</h2>
<div class="card"><table><tr><th>Indicator</th><th>Latest</th><th>Change</th></tr>{rows}</table></div>'''


def _allocation_rows(allocation, portfolio_value):
    rows = ""
    pv = _safe_float(portfolio_value, INITIAL_CAPITAL)
    for ticker, weight in sorted(allocation.items(), key=lambda x: -_safe_float(x[1])):
        w = _safe_float(weight)
        eur = pv * w
        rows += f'<tr><td>{ticker}</td><td>{w*100:.1f}%</td><td>EUR {eur:,.0f}</td></tr>'
    return rows


def _benchmark_rows(metrics):
    port_ret = _safe_float(metrics.get("weekly_return"))
    spy_ret = _safe_float(metrics.get("benchmark_spy"))
    ew_ret = _safe_float(metrics.get("benchmark_ew"))
    rp_ret = _safe_float(metrics.get("benchmark_rp"))

    rows = f'<tr><td>Agent Portfolio</td><td class="{_color_class(port_ret)}">{pct_fmt(port_ret)}</td><td>—</td></tr>'
    rows += f'<tr><td>S&P 500 (SPY)</td><td>{pct_fmt(spy_ret)}</td><td class="{_color_class(port_ret - spy_ret)}">{pct_fmt(port_ret - spy_ret)}</td></tr>'
    rows += f'<tr><td>Equal Weight</td><td>{pct_fmt(ew_ret)}</td><td class="{_color_class(port_ret - ew_ret)}">{pct_fmt(port_ret - ew_ret)}</td></tr>'
    rows += f'<tr><td>Risk Parity</td><td>{pct_fmt(rp_ret)}</td><td class="{_color_class(port_ret - rp_ret)}">{pct_fmt(port_ret - rp_ret)}</td></tr>'
    return rows


def _metric_card(label, value, color_it, is_pct=True, prefix=""):
    val = _safe_float(value)
    if prefix:
        display = f"{prefix}{val:,.2f}"
        css_class = ""
    elif is_pct:
        display = pct_fmt(val)
        css_class = _color_class(val) if color_it else ""
    else:
        display = f"{val:.2f}"
        css_class = _color_class(val) if color_it else ""
    return f'<div class="metric"><div class="value {css_class}">{display}</div><div class="label">{label}</div></div>'


def _color_class(value):
    v = _safe_float(value)
    return "positive" if v > 0 else "negative" if v < 0 else "neutral"


def _list_section(items, empty_msg):
    if not items:
        return f"<p>{empty_msg}</p>"
    return "<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def _weights_rows(weights, confidence):
    rows = ""
    for signal in sorted(weights.keys()):
        w = _safe_float(weights.get(signal))
        c = _safe_float(confidence.get(signal, 0.5))
        rows += f'<tr><td>{signal}</td><td>{w*100:.1f}%</td><td>{c*100:.0f}%</td></tr>'
    return rows


def _forward_note(learning_result, metrics, regime):
    errors = learning_result.get("errors", [])
    if len(errors) > 2:
        return "Multiple errors detected. Next week: increase defensive allocation, widen diversification, reduce position sizes in volatile assets."
    elif regime == "crisis":
        return "Crisis regime active. Maintaining maximum defensive posture. Will reassess Monday."
    elif regime == "risk_off":
        return "Risk-off environment. Favor bonds and low-volatility assets. Monitor for regime change signals."
    elif regime == "risk_on":
        return "Risk-on confirmed. Maintain current equity tilt. Watch for momentum exhaustion signals."
    else:
        return "Transition regime. Balanced allocation. Ready to shift if signals strengthen in either direction."


def _equity_curve_section():
    all_perf = storage.get_all_performance()
    if len(all_perf) < 2:
        return ""

    weeks = [p["week_id"] for p in all_perf]
    cum_returns = [(_safe_float(p.get("cumulative_return")) + 1) * INITIAL_CAPITAL for p in all_perf]
    spy_returns = []
    running_spy = INITIAL_CAPITAL
    for p in all_perf:
        running_spy *= (1 + _safe_float(p.get("benchmark_spy")))
        spy_returns.append(running_spy)

    labels = json.dumps([f"W{w}" for w in weeks])
    agent_data = json.dumps([round(v, 2) for v in cum_returns])
    spy_data = json.dumps([round(v, 2) for v in spy_returns])

    return f"""
<h2>Equity Curve</h2>
<div class="card">
  <canvas id="equityChart" height="200"></canvas>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
new Chart(document.getElementById('equityChart'), {{
  type: 'line',
  data: {{
    labels: {labels},
    datasets: [
      {{ label: 'Agent', data: {agent_data}, borderColor: '#58a6ff', backgroundColor: 'transparent', tension: 0.3 }},
      {{ label: 'SPY Benchmark', data: {spy_data}, borderColor: '#8b949e', backgroundColor: 'transparent', borderDash: [5,5], tension: 0.3 }}
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#8b949e' }}, grid: {{ color: '#30363d' }} }},
      y: {{ ticks: {{ color: '#8b949e', callback: v => 'EUR ' + v.toLocaleString() }}, grid: {{ color: '#30363d' }} }}
    }}
  }}
}});
</script>"""


def _update_history_index():
    """Create a simple index page listing all weekly reports."""
    files = sorted([f for f in os.listdir(HISTORY_PATH) if f.startswith("week-") and f.endswith(".html")])
    links = ""
    for f in reversed(files):
        week_num = f.replace("week-", "").replace(".html", "")
        links += f'<li><a href="history/{f}">Week {week_num} Report</a></li>\n'

    if not links:
        return

    index_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Report Archive</title>
<style>body{{font-family:sans-serif;background:#0d1117;color:#c9d1d9;padding:20px;max-width:600px;margin:0 auto}}
a{{color:#58a6ff}}h1{{margin-bottom:16px}}li{{margin:8px 0}}</style></head>
<body><h1>Weekly Report Archive</h1><ul>{links}</ul></body></html>"""

    with open(os.path.join(HISTORY_PATH, "index.html"), "w") as f:
        f.write(index_html)
