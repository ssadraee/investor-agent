# CLAUDE.md — Investor Agent

## Project Overview
- Autonomous portfolio manager running on €10,000 virtual capital, executing a weekly investment cycle using ETF data.
- Classifies market regimes (rule-based), optimizes allocations (mean-variance), and self-adapts signal weights (Bayesian).
- Runs entirely on GitHub Actions + GitHub Pages; no server required.

## Tech Stack
- **Language:** Python 3.11
- **Key libraries:** `yfinance`, `fredapi`, `requests`, `scipy` (SLSQP optimizer), `pandas`, `numpy`
- **Storage:** SQLite (`data/agent.db`) — no external DB
- **Reporting:** Static HTML → GitHub Pages + Gmail SMTP

## Repository Structure
```
agent/          # Main Python package (all logic lives here)
  main.py       # Entry point; dispatches phases
  config.py     # All constants, universe, regime budgets, paths
  scanner.py    # Fetches market data (yfinance + FRED), computes signals across US + global markets
  datasources.py  # External free data sources (World Bank, IMF, OECD, GDELT, ECB, ACLED, NewsAPI)
  regime.py     # Classifies market into 4 regimes via 12-signal weighted composite score
  allocator.py  # MVO portfolio optimization (scipy SLSQP)
  evaluator.py  # Weekly performance metrics vs 3 benchmarks
  learner.py    # Bayesian signal weight adaptation
  storage.py    # SQLite read/write (6 tables)
  reporter.py   # HTML report generation + email dispatch
  utils.py      # Shared math helpers (Sharpe, Sortino, drawdown, etc.)
data/           # SQLite database (agent.db)
docs/           # Generated HTML reports (GitHub Pages root)
  history/      # Per-week report archive
.github/
  workflows/    # monday.yml, friday.yml, sunday.yml (3 cron jobs)
```

## Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Run individual phases
python -m agent.main --phase scan_and_allocate   # Monday logic
python -m agent.main --phase evaluate            # Friday logic
python -m agent.main --phase learn_and_report    # Sunday logic
python -m agent.main --phase full_cycle          # All 3 in sequence

# No build step, no dev server, no test suite defined
```

## Architecture & Patterns
- **Pipeline:** scanner → regime → allocator → storage → evaluator → learner → reporter
- **Scheduled via GitHub Actions cron** (Mon 10:30, Fri 21:00, Sun 12:00 UTC); each workflow commits results back to the repo.
- **State stored immutably in SQLite** — each week appends a new record; no in-place updates.
- **Fallback chain in allocator:** MVO → inverse-volatility → equal-weight if fewer than 3 assets survive post-processing.
- **Learning is conservative:** ±20% max drift from default weights; only activates fully after 8 weeks of data; 0.95 forgetting factor.
- **All configurable parameters in `config.py`** — never hardcoded in module logic.
- **`classify_regime()` receives the full `market_state` dict** (not just bare signals), enabling all 12 regime score dimensions to draw on global data from scanner and external sources.

## Key Files & Modules
| File | Why it matters |
|------|----------------|
| `agent/config.py` | Single source of truth: universe, regime budgets, paths, email config, SIGNALS list |
| `agent/main.py` | Phase dispatcher; start here to trace any workflow |
| `agent/scanner.py` | All market data fetching; `scan_market()` is the top-level call; outputs full `market_state` dict |
| `agent/datasources.py` | `fetch_external_sources()` — World Bank, IMF, OECD CLI, GDELT, ECB, ACLED (optional), NewsAPI (optional) |
| `agent/regime.py` | `classify_regime(market_state)` → scores 12 signal dimensions → returns `(regime_name, confidence, scores)` |
| `agent/allocator.py` | `build_allocation()` → dict of `{ticker: weight, "CASH": weight}` |
| `agent/storage.py` | All DB interactions; `init_db()` must be called first |
| `.github/workflows/` | Defines the full operational schedule and secrets injected |

## Dependencies & Integrations
- **FRED API** (`fredapi`) — US + international macro (yield curve, unemployment, CPI, Fed Funds, credit spreads, EPU, EA/UK/Japan rates)
- **yfinance** — daily OHLCV for 19 UCITS ETFs + VIX + 11 global equity indices + 8 FX pairs + 7 commodity futures
- **World Bank Open Data** — governance indicators (political stability, rule of law) and macro per country; no key required
- **IMF DataMapper** — GDP growth and inflation forecasts by country; no key required
- **OECD SDMX-JSON API** — Composite Leading Indicators (CLI) per country; no key required
- **GDELT 2.0 DOC API** — global event conflict intensity (30-day timelines, 6 geopolitical themes); no key required
- **ECB Statistical Data Warehouse** — ECB key rates + M3 money supply (CSV format); no key required
- **ACLED** — armed conflict events by region (optional; requires free registration)
- **NewsAPI** — headline sentiment by topic (optional; free tier available)
- **Gmail SMTP** — email delivery of reports

### Required environment variables / GitHub Secrets
- `FRED_API_KEY` — from fred.stlouisfed.org (free)
- `EMAIL_SENDER` — Gmail address used to send reports
- `EMAIL_APP_PASSWORD` — Gmail App Password (requires 2FA on account)
- `EMAIL_RECIPIENT` — destination email for reports

### Optional environment variables (unlock additional data sources)
- `ACLED_API_KEY` + `ACLED_EMAIL` — armed conflict event data (acleddata.com, free registration)
- `NEWS_API_KEY` — headline sentiment analysis (newsapi.org, free tier)

## Conventions & Code Style
- Each module exports exactly one top-level orchestrator function (e.g., `scan_market()`, `classify_regime()`, `build_allocation()`).
- All functions use relative imports within the `agent` package.
- Data passed between stages as plain dicts (no dataclasses/Pydantic).
- JSON blobs stored as-is in SQLite `TEXT` columns; parsed on retrieval.
- Logging via `logging.getLogger(__name__)` in every module.

## Known Gotchas
- **`init_db()` must be called** before any storage reads/writes; `main.py` does this, but standalone module testing requires it manually.
- **Covariance matrix may be unavailable** if yfinance returns insufficient data; `allocator.py` falls back to inverse-volatility silently.
- **VIX ticker is `^VIX`** — fetched separately in scanner; if it fails, volatility signals default to neutral.
- **FRED data is monthly/weekly** — scanner forward-fills to align with daily price index.
- **GitHub Actions workflows commit back to the repo** — ensure the workflow has `contents: write` permission (set in repo Settings → Actions → Workflow permissions).
- **Week IDs are integers** from the DB; `get_current_week_id()` returns `None` on empty DB (first run).
- **Learning only affects weights after 8 weeks** — early runs use default signal weights from `config.py`.
- **GitHub Pages must be enabled** (Settings → Pages → source: `main`/`master` branch, `/docs` folder) for reports to be publicly accessible.
- **`SIGNALS` list gates the Bayesian learner** — any score dimension returned by `classify_regime()` that is not in `config.SIGNALS` is silently ignored and never learned from. The list currently has 12 entries (6 original US signals + 6 global).
- **External sources degrade gracefully** — all 6 global regime score dimensions (`global_breadth`, `fx_stress`, `credit_conditions`, `geopolitical_risk`, `leading_indicators`, `global_monetary`) default to `0.0` (neutral) when their source API is unavailable or returns unexpected data.
- **OECD SDMX-JSON format is complex** — `datasources.py` manually parses dimension indices; if the OECD API schema changes, `fetch_oecd_cli()` may silently return empty data.
