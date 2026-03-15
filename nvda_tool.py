#!/usr/bin/env python3
"""Market dashboard data generator for NVDA, SOXL, NVDL, and TSLA."""
from __future__ import annotations

import json
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

DATA_DIR = Path("data")
OUTPUT_DIR = Path("output")
PORTAL_DIR = Path("portal")

EASTERN_TZ = ZoneInfo("America/New_York")
AFTER_HOURS_START = time(16, 0)
PRE_MARKET_START = time(7, 0)
REGULAR_OPEN = time(9, 30)

TICKERS: List[str] = ["NVDA", "SOXL", "NVDL", "TSLA"]

PERFORMANCE_WINDOWS = {
    "1d": 1,
    "3d": 3,
    "5d": 5,
    "1mo": 21,   # ~1 trading month
    "1y": 252,   # ~1 trading year
}

MARKET_SUMMARY_PATH = OUTPUT_DIR / "market_summary.json"
PORTAL_PAGE_PATH = PORTAL_DIR / "market-dashboard.html"
PORTAL_SUMMARY_PATH = PORTAL_DIR / "market_summary.json"


def ensure_directories() -> None:
    for path in (DATA_DIR, OUTPUT_DIR, PORTAL_DIR):
        path.mkdir(parents=True, exist_ok=True)


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def fetch_price_history(symbol: str) -> pd.DataFrame:
    df = yf.download(
        symbol,
        period="max",
        interval="1d",
        auto_adjust=False,
        progress=False,
    )

    if df.empty:
        raise RuntimeError(f"Received empty dataset for {symbol}")

    df = flatten_columns(df)
    df.index.name = "Date"
    df = df.reset_index()
    df["Date"] = pd.to_datetime(df["Date"])
    return df


def compute_performance(df: pd.DataFrame) -> Dict[str, Optional[float]]:
    closes = df.sort_values("Date")["Close"].reset_index(drop=True)
    performances: Dict[str, Optional[float]] = {}

    for label, periods in PERFORMANCE_WINDOWS.items():
        if len(closes) <= periods:
            performances[label] = None
            continue
        latest_close = closes.iloc[-1]
        reference_close = closes.iloc[-(periods + 1)]
        performances[label] = float((latest_close / reference_close) - 1)

    ath_close = closes.max()
    latest_close = closes.iloc[-1]
    performances["ath"] = float((latest_close / ath_close) - 1)
    return performances


def timestamp_in_window(
    timestamp: Optional[int], start: time, end: time, wrap: bool = False
) -> bool:
    if timestamp is None:
        return False
    try:
        dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).astimezone(EASTERN_TZ)
    except (ValueError, OSError):
        return False
    current_time = dt.time()
    if wrap:
        return current_time >= start or current_time < end
    return start <= current_time < end


def fetch_session_changes(symbol: str, latest_close: float) -> Dict[str, Optional[float]]:
    pre_market_change = None
    after_hours_change = None

    try:
        info = yf.Ticker(symbol).get_info()
    except Exception:
        info = {}

    latest_close = float(latest_close)
    if latest_close <= 0:
        return {"pre_market": None, "after_hours": None}

    pre_price = info.get("preMarketPrice")
    pre_time = info.get("preMarketTime")
    if (
        pre_price is not None
        and timestamp_in_window(pre_time, PRE_MARKET_START, REGULAR_OPEN)
    ):
        pre_market_change = float(pre_price) / latest_close - 1

    post_price = info.get("postMarketPrice")
    post_time = info.get("postMarketTime")
    if (
        post_price is not None
        and timestamp_in_window(post_time, AFTER_HOURS_START, PRE_MARKET_START, wrap=True)
    ):
        after_hours_change = float(post_price) / latest_close - 1

    return {"pre_market": pre_market_change, "after_hours": after_hours_change}


def serialize_summary(symbol: str, df: pd.DataFrame) -> Dict[str, object]:
    performance = compute_performance(df)
    latest_close = float(df.sort_values("Date")["Close"].iloc[-1])
    session = fetch_session_changes(symbol, latest_close)
    summary = {
        "symbol": symbol,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "records": int(len(df)),
        "latest_close": latest_close,
        "performance": performance,
        "session": session,
    }

    symbol_path = OUTPUT_DIR / f"{symbol.lower()}_summary.json"
    with symbol_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    # Maintain legacy NVDA summary path for compatibility
    if symbol.upper() == "NVDA":
        with (OUTPUT_DIR / "nvda_summary.json").open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    return summary


def write_price_file(symbol: str, df: pd.DataFrame) -> None:
    data_path = DATA_DIR / f"{symbol.lower()}_prices.csv"
    df.to_csv(data_path, index=False)

    if symbol.upper() == "NVDA":
        legacy_path = DATA_DIR / "nvda_prices.csv"
        df.to_csv(legacy_path, index=False)


def render_dashboard(summaries: Dict[str, Dict[str, object]]) -> None:
    summary_json = json.dumps(summaries).replace("</", "<\\/")
    ticker_array = json.dumps(TICKERS)
    perf_order = json.dumps(["1d", "3d", "5d", "1mo", "1y", "ath"])

    html_template = """<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <title>Market Performance Dashboard</title>
    <style>
      body { font-family: 'Inter', system-ui, sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0; }
      table { width: 100%; border-collapse: collapse; margin-top: 1.5rem; }
      th, td { border: 1px solid #1e293b; padding: 0.75rem; text-align: center; }
      th { background: #1e293b; text-transform: uppercase; font-size: 0.8rem; letter-spacing: 0.08em; }
      tr:nth-child(even) { background: #111827; }
      tr:nth-child(odd) { background: #0f172a; }
      td:first-child { font-weight: 600; text-align: left; padding-left: 1rem; }
      .timestamp { margin-top: 1rem; font-size: 0.9rem; color: #94a3b8; }
      .refresh-row { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
      .refresh-btn { background: #38bdf8; border: none; color: #0f172a; padding: 0.6rem 1.4rem; border-radius: 999px; font-weight: 600; cursor: pointer; box-shadow: 0 4px 10px rgba(56, 189, 248, 0.35); transition: background 0.2s ease; }
      .refresh-btn:hover { background: #0ea5e9; }
      .refresh-btn:disabled { opacity: 0.65; cursor: not-allowed; box-shadow: none; }
      .status { font-size: 0.9rem; color: #94a3b8; }
      .positive { color: #22c55e; }
      .negative { color: #f87171; }
    </style>
  </head>
  <body>
    <h1>Market Performance Dashboard</h1>
    <p>Daily OHLCV data sourced via Yahoo Finance. Percentage changes compare the latest close with prior trading closes for each horizon. \"ATH\" shows performance relative to the all-time closing high.</p>
    <div class=\"refresh-row\">
      <button class=\"refresh-btn\" id=\"refresh-btn\" type=\"button\">↻ Refresh data</button>
      <p class=\"status\" id=\"status-message\">Loaded cached data.</p>
    </div>
    <table>
      <thead>
        <tr>
          <th>Ticker</th>
          <th>1D</th>
          <th>3D</th>
          <th>5D</th>
          <th>1MO</th>
          <th>1Y</th>
          <th>ATH</th>
          <th>PRE-MARKET</th>
          <th>AFTER-HOURS</th>
        </tr>
      </thead>
      <tbody id=\"market-table-body\"></tbody>
    </table>
    <p class=\"timestamp\" id=\"timestamp\"></p>

    <script>
      const TICKERS = %%TICKER_ARRAY%%;
      const PERFORMANCE_ORDER = %%PERFORMANCE_ORDER%%;
      let currentData = %%SUMMARY_DATA%%;

      const tableBody = document.getElementById('market-table-body');
      const statusMessage = document.getElementById('status-message');
      const timestampEl = document.getElementById('timestamp');
      const refreshBtn = document.getElementById('refresh-btn');

      function formatPercent(value) {
        if (value === null || value === undefined || Number.isNaN(value)) return 'N/A';
        return `${(value * 100).toFixed(2)}%`;
      }

      function wrapTrend(value) {
        if (value === null || value === undefined || Number.isNaN(value)) return '<td>N/A</td>';
        const trendClass = value > 0 ? 'positive' : value < 0 ? 'negative' : '';
        return `<td><span class="${trendClass}">${formatPercent(value)}</span></td>`;
      }

      function renderTable(data) {
        let rows = '';
        TICKERS.forEach((symbol) => {
          const summary = data[symbol];
          if (!summary) return;
          const perf = summary.performance || {};
          const session = summary.session || {};
          const perfCells = PERFORMANCE_ORDER.map((window) => wrapTrend(perf[window] ?? null)).join('');
          const pre = wrapTrend(session.pre_market ?? null);
          const after = wrapTrend(session.after_hours ?? null);
          rows += `<tr><td>${symbol}</td>${perfCells}${pre}${after}</tr>`;
        });
        tableBody.innerHTML = rows;
        updateTimestamp(data);
      }

      function updateTimestamp(data) {
        const sourceSymbol = TICKERS.find((symbol) => data[symbol]);
        if (!sourceSymbol) {
          timestampEl.textContent = 'No timestamp available.';
          return;
        }
        const iso = data[sourceSymbol].last_updated;
        if (!iso) {
          timestampEl.textContent = 'No timestamp available.';
          return;
        }
        const date = new Date(iso);
        timestampEl.textContent = `Last updated: ${date.toLocaleString()} (${date.toUTCString()})`;
      }

      async function refreshData() {
        refreshBtn.disabled = true;
        statusMessage.textContent = 'Fetching latest data…';
        try {
          const response = await fetch('market_summary.json?ts=' + Date.now(), { cache: 'no-store' });
          if (!response.ok) throw new Error('Failed to load market_summary.json');
          currentData = await response.json();
          renderTable(currentData);
          statusMessage.textContent = 'Data refreshed successfully.';
        } catch (error) {
          console.error(error);
          statusMessage.textContent = 'Unable to refresh data. Check the server logs or rerun nvda_tool.py.';
        } finally {
          refreshBtn.disabled = false;
        }
      }

      refreshBtn.addEventListener('click', refreshData);
      renderTable(currentData);
    </script>
  </body>
</html>
"""

    html = (
        html_template.replace("%%SUMMARY_DATA%%", summary_json)
        .replace("%%TICKER_ARRAY%%", ticker_array)
        .replace("%%PERFORMANCE_ORDER%%", perf_order)
    )

    with PORTAL_PAGE_PATH.open("w", encoding="utf-8") as f:
        f.write(html)


def main() -> None:
    ensure_directories()
    summaries: Dict[str, Dict[str, object]] = {}

    for symbol in TICKERS:
        df = fetch_price_history(symbol)
        write_price_file(symbol, df)
        summaries[symbol] = serialize_summary(symbol, df)

    with MARKET_SUMMARY_PATH.open("w", encoding="utf-8") as f:
        json.dump(summaries, f, indent=2)
    with PORTAL_SUMMARY_PATH.open("w", encoding="utf-8") as f:
        json.dump(summaries, f, indent=2)

    render_dashboard(summaries)
    print(
        "Updated price files under data/, summaries under output/ + portal/, and portal/market-dashboard.html"
    )


if __name__ == "__main__":
    main()
