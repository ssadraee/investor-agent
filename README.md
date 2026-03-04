# Autonomous Investor Agent

A self-improving, autonomous virtual portfolio manager that optimizes **risk-adjusted returns** on €10,000 of virtual capital.

Runs entirely on **GitHub Actions** (free). Reports published to **GitHub Pages** (free). Weekly email to your inbox.

## How It Works

| Day | Phase | What Happens |
|-----|-------|-------------|
| **Monday 10:30 UTC** | Scan & Allocate | Fetches market data, classifies regime, builds risk-optimized portfolio |
| **Friday 21:00 UTC** | Evaluate | Computes weekly return, Sharpe, drawdown, compares vs benchmarks |
| **Sunday 12:00 UTC** | Learn & Report | Updates signal weights, generates HTML report, sends email |

## Setup (One-Time, ~10 Minutes)

### 1. Create Repository
- Create a **new public repository** on GitHub named `investor-agent`
- Upload all files from this project

### 2. Enable GitHub Pages
- Go to **Settings → Pages**
- Source: **Deploy from a branch**
- Branch: `main`, folder: `/docs`
- Save

### 3. Add Repository Secrets
Go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value | How to Get |
|--------|-------|-----------|
| `FRED_API_KEY` | Your FRED API key | Free at [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `EMAIL_SENDER` | Gmail address to send from | Any Gmail account |
| `EMAIL_APP_PASSWORD` | Gmail App Password | [Google Account → Security → 2-Step → App Passwords](https://myaccount.google.com/apppasswords) |
| `EMAIL_RECIPIENT` | Your personal email to receive reports | e.g. your Hotmail address |

### 4. Enable Workflow Permissions
- Go to **Settings → Actions → General**
- Under "Workflow permissions", select **Read and write permissions**
- Save

### 5. Done!
The agent runs automatically on schedule. To test immediately:
- Go to **Actions** tab → select any workflow → **Run workflow**

## View Reports
- **Latest report**: `https://YOUR_USERNAME.github.io/investor-agent/`
- **Report archive**: `https://YOUR_USERNAME.github.io/investor-agent/history/`

## Architecture

```
agent/
├── main.py        # Entry point, phase dispatcher
├── scanner.py     # Market data (yfinance + FRED)
├── regime.py      # Regime classification (risk_on/off/transition/crisis)
├── allocator.py   # Mean-variance optimization with constraints
├── evaluator.py   # Performance metrics & benchmark comparison
├── learner.py     # Bayesian signal weight updates
├── reporter.py    # HTML report generation + email
├── storage.py     # SQLite persistence
└── config.py      # Parameters & universe
```

## Investment Rules
- Long-only stocks & ETFs
- No leverage, no shorting, no derivatives
- Max 40% per position
- Minimum 3 assets
- 0.10% transaction cost assumption
- Cash allowed only as risk hedge

## Benchmarks
Compared weekly against: S&P 500 (SPY), Equal-Weight, Risk-Parity

## Disclaimer
This is a **virtual portfolio simulation** for educational purposes only. No real money is at risk. Not financial advice. Past simulated performance does not indicate future results.
