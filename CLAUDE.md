# CLAUDE.md — Investor Agent

## Project Overview
- Autonomous portfolio manager running on €10,000 virtual capital, executing a weekly investment cycle using ETF data.
- Classifies market regimes (rule-based), optimizes allocations (mean-variance), and self-adapts signal weights (Bayesian).
- Runs entirely on GitHub Actions + GitHub Pages; no server required.

## Tech Stack
- **Language:** Python 3.11
- **Key libraries:** `yfinance`, `fredapi`, `scipy` (SLSQP optimizer), `pandas`, `numpy`
- **Storage:** SQLite (`data/agent.db`) — no external DB
- **Reporting:** Static HTML → GitHub Pages + Gmail SMTP

## Repository Structure
```
agent/          # Main Python package (all logic lives here)
  main.py       # Entry point; dispatches phases
  config.py     # All constants, universe, regime budgets, paths
  scanner.py    # Fetches market data (yfinance + FRED), computes 20+ signals
  regime.py     # Classifies market into 4 regimes via weighted composite score
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

## Key Files & Modules
| File | Why it matters |
|------|----------------|
| `agent/config.py` | Single source of truth: universe, regime budgets, paths, email config |
| `agent/main.py` | Phase dispatcher; start here to trace any workflow |
| `agent/scanner.py` | All external data fetching; `scan_market()` is the top-level call |
| `agent/regime.py` | `classify_regime()` → returns `(regime_name, confidence, scores)` |
| `agent/allocator.py` | `build_allocation()` → dict of `{ticker: weight, "CASH": weight}` |
| `agent/storage.py` | All DB interactions; `init_db()` must be called first |
| `.github/workflows/` | Defines the full operational schedule and secrets injected |

## Dependencies & Integrations
- **FRED API** (`fredapi`) — macro data (yield curve, unemployment, CPI, Fed Funds)
- **yfinance** — daily OHLCV for 19 ETFs + VIX
- **Gmail SMTP** — email delivery of reports

### Required environment variables / GitHub Secrets
- `FRED_API_KEY` — from fred.stlouisfed.org (free)
- `EMAIL_SENDER` — Gmail address used to send reports
- `EMAIL_APP_PASSWORD` — Gmail App Password (requires 2FA on account)
- `EMAIL_RECIPIENT` — destination email for reports

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
