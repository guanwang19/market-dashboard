# Market Performance Tool

This utility pulls daily OHLCV history for NVDA, SOXL, NVDL, and TSLA via [yfinance](https://github.com/ranaroussi/yfinance), computes multiple return horizons (1d/3d/5d/1mo/1y) plus drawdown from all-time high, captures pre-market and after-hours change percentages, and renders both data files and a portal-ready dashboard.

## Outputs

- `data/<ticker>_prices.csv` – Daily OHLCV data for each tracked symbol (legacy `data/nvda_prices.csv` retained for compatibility).
- `output/<ticker>_summary.json` – Per-ticker metadata, performance windows, and session stats (legacy `output/nvda_summary.json` remains).
- `output/market_summary.json` – Aggregated view covering every ticker.
- `portal/market-dashboard.html` – Static HTML table linked from `PORTAL.md` for quick viewing inside the Control UI portal.

## Setup

The repo currently uses a uv-managed virtual environment in `.venv/` (no `activate` script). You can either:

```bash
# Option A: reuse the bundled venv interpreter
/home/guan/.openclaw/workspace/.venv/bin/python nvda_tool.py

# Option B: create your own env
python -m venv .venv_standard  # requires python3-venv on system
source .venv_standard/bin/activate
pip install -r requirements.txt
```

## Usage

From the workspace root:

```bash
python nvda_tool.py  # or use the explicit interpreter path shown above
```

The script will:

1. Download history for every ticker.
2. Write/refresh the CSV + JSON artifacts under `data/` and `output/`.
3. Regenerate `portal/market-dashboard.html` so the Control UI portal shows the updated percentages.

## Performance Windows

Simple percentage returns (latest close vs. close *n* trading days ago) are calculated for:

- `1d`, `3d`, `5d`
- `1mo` (~21 trading days)
- `1y` (~252 trading days)
- `ath` – Drawdown from the all-time closing high

Pre-market and after-hours percentages come from Yahoo Finance quote data and surface as soon as the feed provides them (they may be `N/A` outside those sessions). Adjust tickers or windows via the `TICKERS` and `PERFORMANCE_WINDOWS` constants in `nvda_tool.py`.
