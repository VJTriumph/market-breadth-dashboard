import json
import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).parent
STOCKS_FILE = BASE / "data" / "stocks.csv"
DATAFILE = BASE / "data" / "dashboard.csv"
TEMPLATE = BASE / "market_breadth_dashboard.html"
OUTPUT = BASE / "output" / "market_breadth_dashboard_output.html"

MA_PERIODS = [20, 50, 200]
RSI_PERIOD = 14
HISTORY_DAYS = 420  # enough for 200MA + RSI warmup


def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def fetch_prices(tickers):
    """Fetch closing prices for all tickers in one batch call."""
    ns_tickers = [t + ".NS" for t in tickers]
    end = datetime.today()
    start = end - timedelta(days=HISTORY_DAYS)
    print(f"Fetching {len(ns_tickers)} tickers from {start.date()} to {end.date()}...")
    raw = yf.download(
        ns_tickers,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw[["Close"]]
        closes.columns = ns_tickers
    # Strip .NS suffix back
    closes.columns = [c.replace(".NS", "") for c in closes.columns]
    return closes


def stock_signals(close_series):
    """Return dict of signals for a single stock's close series."""
    s = close_series.dropna()
    if len(s) < 5:
        return None
    signals = {}
    last = s.iloc[-1]
    # Moving average signals
    for ma in MA_PERIODS:
        if len(s) >= ma:
            ma_val = s.rolling(ma).mean().iloc[-1]
            signals[f"above_{ma}ma"] = 1 if last > ma_val else 0
        else:
            signals[f"above_{ma}ma"] = 0
    # RSI signal
    if len(s) >= RSI_PERIOD + 1:
        rsi = compute_rsi(s, RSI_PERIOD).iloc[-1]
        signals["rsi_above_50"] = 1 if rsi > 50 else 0
    else:
        signals["rsi_above_50"] = 0
    # Weekly return (5-day)
    if len(s) >= 6:
        week_ret = (last / s.iloc[-6] - 1) * 100
        signals["weekly_return_positive"] = 1 if week_ret > 0 else 0
    else:
        signals["weekly_return_positive"] = 0
    return signals


def compute_edge_score(row):
    """
    EdgeScore = weighted sum:
      20MA: 15, 50MA: 20, 200MA: 25, RSI>50: 20, WeeklyReturn: 20
    Returns 0-100 score (same weights as reference app).
    """
    weights = {"20MA": 15, "50MA": 20, "200MA": 25, "RSI>50": 20, "WeeklyReturn": 20}
    score = (
        row["20MA"] / 100 * weights["20MA"]
        + row["50MA"] / 100 * weights["50MA"]
        + row["200MA"] / 100 * weights["200MA"]
        + row["RSI>50"] / 100 * weights["RSI>50"]
        + row["WeeklyReturn"] / 100 * weights["WeeklyReturn"]
    )
    return round(score, 2)


def status_from_edge(edge):
    if edge >= 60:
        return "Strong"
    elif edge >= 40:
        return "Moderate"
    elif edge >= 20:
        return "Weak"
    else:
        return "No Edge"


def build_dashboard():
    # Load stock-sector mapping; fix "Auo Index" typo -> "Auto Index"
    stocks_df = pd.read_csv(STOCKS_FILE)
    stocks_df["sector"] = stocks_df["sector"].str.strip()
    stocks_df["sector"] = stocks_df["sector"].replace("Auo Index", "Auto Index")
    stocks_df["stock"] = stocks_df["stock"].str.strip()

    tickers = stocks_df["stock"].unique().tolist()
    prices = fetch_prices(tickers)

    # Compute per-stock signals
    rows = []
    for _, row in stocks_df.iterrows():
        ticker = row["stock"]
        sector = row["sector"]
        if ticker not in prices.columns:
            print(f"  MISSING: {ticker}")
            continue
        sig = stock_signals(prices[ticker])
        if sig is None:
            print(f"  NO DATA: {ticker}")
            continue
        sig["stock"] = ticker
        sig["sector"] = sector
        rows.append(sig)

    sig_df = pd.DataFrame(rows)

    # Aggregate per sector
    sector_rows = []
    for sector, grp in sig_df.groupby("sector"):
        n = len(grp)
        p20 = round(grp["above_20ma"].sum() / n * 100, 2)
        p50 = round(grp["above_50ma"].sum() / n * 100, 2)
        p200 = round(grp["above_200ma"].sum() / n * 100, 2)
        prsi = round(grp["rsi_above_50"].sum() / n * 100, 2)
        pweek = round(grp["weekly_return_positive"].sum() / n * 100, 2)
        sector_rows.append({
            "Sector": sector,
            "20MA": p20,
            "50MA": p50,
            "200MA": p200,
            "RSI>50": prsi,
            "WeeklyReturn": pweek,
        })

    df = pd.DataFrame(sector_rows)
    df["EdgeScore"] = df.apply(compute_edge_score, axis=1)
    df = df.sort_values("EdgeScore", ascending=False).reset_index(drop=True)
    df["Rank"] = df.index + 1

    # Relative edge vs average
    avg_edge = df["EdgeScore"].mean()
    df["RelativeEdge"] = (df["EdgeScore"] - avg_edge).round(2)

    df["Status"] = df["EdgeScore"].apply(status_from_edge)

    # Save dashboard CSV
    df.to_csv(DATAFILE, index=False)
    print(f"Saved dashboard.csv ({len(df)} sectors)")

    # Build HTML output
    dashboard_json = json.dumps(
        df.rename(columns={
            "Sector": "sector", "20MA": "p20", "50MA": "p50",
            "200MA": "p200", "RSI>50": "prsi", "WeeklyReturn": "pweek",
            "EdgeScore": "edge", "Rank": "rank", "RelativeEdge": "relative",
            "Status": "status",
        }).to_dict(orient="records"),
        indent=2,
    )

    html = TEMPLATE.read_text()
    start = html.find("const dashboardData =")
    end = html.find("];", start)
    new_html = html[:start] + "const dashboardData = " + dashboard_json + html[end + 2:]
    OUTPUT.write_text(new_html)
    print(f"Dashboard created: {OUTPUT}")


if __name__ == "__main__":
    build_dashboard()
