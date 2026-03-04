"""
Reporter — Generates HTML weekly reports for GitHub Pages and sends email.
"""
import os
import json
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from agent.config import (
    EMAIL_RECIPIENT, EMAIL_SENDER, EMAIL_APP_PASSWORD,
    DOCS_PATH, HISTORY_PATH, INITIAL_CAPITAL
)
from agent import storage
from agent.utils import pct_fmt

logger = logging.getLogger(__name__)


def generate_report(week_id, market_state, regime, regime_confidence,
                    allocation, metrics, learning_result):
    """Generate full HTML report. Returns HTML string."""
    signals = market_state.get("signals", {})
    macro = market_state.get("macro", {})

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
     &nbsp; Confidence: {regime_confidence*100:.0f}%</p>
  <p style="margin-top:8px">VIX: {signals.get('vix_current', 'N/A'):.1f} &nbsp;|&nbsp;
     SPY Momentum (21d): {pct_fmt(signals.get('spy_momentum_21d'))} &nbsp;|&nbsp;
     Yield Spread: {signals.get('yield_spread', 0):.2f} &nbsp;|&nbsp;
     Breadth: {signals.get('breadth_positive', 0)*100:.0f}%</p>
</div>

<h2>2. Signals Summary</h2>
<div class="card">
  <table>
    <tr><th>Signal</th><th>Value</th></tr>
    <tr><td>VIX Current</td><td>{signals.get('vix_current', 'N/A'):.1f}</td></tr>
    <tr><td>VIX 20-day MA</td><td>{signals.get('vix_ma20', 'N/A'):.1f}</td></tr>
    <tr><td>SPY Momentum 63d</td><td>{pct_fmt(signals.get('spy_momentum_63d'))}</td></tr>
    <tr><td>SPY Momentum 21d</td><td>{pct_fmt(signals.get('spy_momentum_21d'))}</td></tr>
    <tr><td>Equity-Bond Correlation</td><td>{signals.get('equity_bond_corr_21d', 0):.3f}</td></tr>
    <tr><td>Vol Risk Premium</td><td>{signals.get('vol_risk_premium', 0):.2f}</td></tr>
    <tr><td>Market Breadth</td><td>{signals.get('breadth_positive', 0)*100:.0f}% positive</td></tr>
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
  {_metric_card("Portfolio Value", metrics.get('portfolio_value', INITIAL_CAPITAL), False, prefix="€")}
  {_metric_card("Sharpe Ratio", metrics.get('sharpe', 0), True, is_pct=False)}
  {_metric_card("Sortino Ratio", metrics.get('sortino', 0), True, is_pct=False)}
  {_metric_card("Max Drawdown", metrics.get('max_drawdown', 0), True)}
  {_metric_card("Annualized Vol", metrics.get('volatility', 0), False)}
  {_metric_card("Transaction Cost", metrics.get('transaction_cost', 0), False, prefix="€")}
</div>

<h2>5. Benchmark Comparison</h2>
<div class="card">
  <table>
    <tr><th>Strategy</th><th>Weekly Return</th><th>vs Agent</th></tr>
    <tr><td>Agent Portfolio</td><td class="{_color_class(metrics.get('weekly_return', 0))}">{pct_fmt(metrics.get('weekly_return', 0))}</td><td>—</td></tr>
    <tr><td>S&P 500 (SPY)</td><td>{pct_fmt(metrics.get('benchmark_spy', 0))}</td>
        <td class="{_color_class((metrics.get('weekly_return', 0) or 0) - (metrics.get('benchmark_spy', 0) or 0))}">{pct_fmt((metrics.get('weekly_return', 0) or 0) - (metrics.get('benchmark_spy', 0) or 0))}</td></tr>
    <tr><td>Equal Weight</td><td>{pct_fmt(metrics.get('benchmark_ew', 0))}</td>
        <td class="{_color_class((metrics.get('weekly_return', 0) or 0) - (metrics.get('benchmark_ew', 0) or 0))}">{pct_fmt((metrics.get('weekly_return', 0) or 0) - (metrics.get('benchmark_ew', 0) or 0))}</td></tr>
    <tr><td>Risk Parity</td><td>{pct_fmt(metrics.get('benchmark_rp', 0))}</td>
        <td class="{_color_class((metrics.get('weekly_return', 0) or 0) - (metrics.get('benchmark_rp', 0) or 0))}">{pct_fmt((metrics.get('weekly_return', 0) or 0) - (metrics.get('benchmark_rp', 0) or 0))}</td></tr>
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


def save_report(week_id, html):
    """Save report to docs/ for GitHub Pages."""
    os.makedirs(HISTORY_PATH, exist_ok=True)

    # Save weekly archive
    filepath = os.path.join(HISTORY_PATH, f"week-{week_id}.html")
    with open(filepath, "w") as f:
        f.write(html)

    # Update index.html with latest report
    index_path = os.path.join(DOCS_PATH, "index.html")
    with open(index_path, "w") as f:
        f.write(html)

    # Generate history index
    _update_history_index()

    logger.info(f"Report saved: {filepath}")
    return filepath


def send_email(week_id, html):
    """Send weekly report via email."""
    if not EMAIL_SENDER or not EMAIL_APP_PASSWORD:
        logger.warning("Email not configured — skipping email send")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Investor Agent — Week {week_id} Report"
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


# === HELPER FUNCTIONS ===

def _macro_section(macro):
    if not macro:
        return '<h2>Macro Data</h2><div class="card"><p>FRED data unavailable (no API key or fetch failed)</p></div>'
    rows = ""
    for key, data in macro.items():
        rows += f'<tr><td>{data["name"]}</td><td>{data["latest"]:.2f}</td><td>{data.get("change", 0):+.3f}</td></tr>'
    return f'''<h2>Macro Data (FRED)</h2>
<div class="card"><table><tr><th>Indicator</th><th>Latest</th><th>Change</th></tr>{rows}</table></div>'''


def _allocation_rows(allocation, portfolio_value):
    rows = ""
    for ticker, weight in sorted(allocation.items(), key=lambda x: -x[1]):
        eur = portfolio_value * weight
        rows += f'<tr><td>{ticker}</td><td>{weight*100:.1f}%</td><td>€{eur:,.0f}</td></tr>'
    return rows


def _metric_card(label, value, color_it, is_pct=True, prefix=""):
    if value is None:
        display = "N/A"
        css_class = "neutral"
    elif prefix:
        display = f"{prefix}{value:,.2f}"
        css_class = ""
    elif is_pct:
        display = pct_fmt(value)
        css_class = _color_class(value) if color_it else ""
    else:
        display = f"{value:.2f}"
        css_class = _color_class(value) if color_it else ""
    return f'<div class="metric"><div class="value {css_class}">{display}</div><div class="label">{label}</div></div>'


def _color_class(value):
    if value is None:
        return "neutral"
    return "positive" if value > 0 else "negative" if value < 0 else "neutral"


def _list_section(items, empty_msg):
    if not items:
        return f"<p>{empty_msg}</p>"
    return "<ul>" + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


def _weights_rows(weights, confidence):
    rows = ""
    for signal in sorted(weights.keys()):
        w = weights[signal]
        c = confidence.get(signal, 0.5)
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
    cum_returns = [((p.get("cumulative_return") or 0) + 1) * INITIAL_CAPITAL for p in all_perf]
    spy_returns = []
    running_spy = INITIAL_CAPITAL
    for p in all_perf:
        running_spy *= (1 + (p.get("benchmark_spy") or 0))
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
      y: {{ ticks: {{ color: '#8b949e', callback: v => '€' + v.toLocaleString() }}, grid: {{ color: '#30363d' }} }}
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
