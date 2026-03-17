import json
import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).parent
STOCKS_FILE = BASE / "data" / "stocks.csv"
DATAFILE    = BASE / "data" / "dashboard.csv"
TEMPLATE    = BASE / "market_breadth_dashboard.html"
OUTPUT      = BASE / "output" / "market_breadth_dashboard_output.html"

MA_PERIODS   = [20, 50, 200]
RSI_PERIOD   = 14
HISTORY_DAYS = 450   # enough for 200-day SMA + RSI warmup


# ── helpers ──────────────────────────────────────────────────────────────────

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder / EWM RSI – same as most retail charting apps."""
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def fetch_prices(tickers: list) -> pd.DataFrame:
    ns = [t + ".NS" for t in tickers]
    end   = datetime.today()
    start = end - timedelta(days=HISTORY_DAYS)
    print(f"Fetching {len(ns)} tickers …")
    raw = yf.download(
        ns,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    closes.columns = [c.replace(".NS", "") for c in closes.columns]
    return closes


def stock_signals(s: pd.Series) -> dict | None:
    """
    Compute all 5 signals for a single stock.

    X% (WeeklyReturn) definition – matches reference app:
      The stock's close this week vs close last week.
      'This week' = latest available close.
      'Last week' = close on the last trading day of the PREVIOUS calendar week
                    (i.e. the Friday before the current Mon–Fri window).
    Signal is 1 if the weekly % change > 0, else 0.
    """
    s = s.dropna()
    if len(s) < 10:
        return None

    last       = s.iloc[-1]
    last_date  = s.index[-1]

    # ── Moving-average signals ────────────────────────────────────────────
    sigs = {}
    for ma in MA_PERIODS:
        if len(s) >= ma:
            ma_val = s.rolling(ma).mean().iloc[-1]
            sigs[f"above_{ma}ma"] = 1 if last > ma_val else 0
        else:
            sigs[f"above_{ma}ma"] = 0

    # ── RSI signal ────────────────────────────────────────────────────────
    if len(s) >= RSI_PERIOD + 1:
        rsi = compute_rsi(s, RSI_PERIOD).iloc[-1]
        sigs["rsi_above_50"] = 1 if (not np.isnan(rsi) and rsi > 50) else 0
    else:
        sigs["rsi_above_50"] = 0

    # ── Weekly-return signal (prev-week close → this-week close) ─────────
    # Find the last trading day that belongs to a DIFFERENT calendar week
    last_week_day = last_date - timedelta(days=last_date.weekday() + 1)   # last Sunday
    # Walk back through the series to find the last bar on or before that Sunday
    prev_week_closes = s[s.index.date <= last_week_day.date()]
    if len(prev_week_closes) >= 1:
        prev_close = prev_week_closes.iloc[-1]
        weekly_ret = (last / prev_close - 1) * 100 if prev_close != 0 else 0
        sigs["weekly_return_positive"] = 1 if weekly_ret > 0 else 0
    else:
        # Fallback: use 5-bar return
        if len(s) >= 6:
            sigs["weekly_return_positive"] = 1 if last > s.iloc[-6] else 0
        else:
            sigs["weekly_return_positive"] = 0

    return sigs


def edge_score(row: pd.Series) -> float:
    """
    Weighted EdgeScore (0–100).
    Weights match reference app: 20MA×15, 50MA×20, 200MA×25, RSI×20, X%×20
    """
    w = {"20MA": 15, "50MA": 20, "200MA": 25, "RSI>50": 20, "WeeklyReturn": 20}
    return round(
        row["20MA"]          / 100 * w["20MA"]
        + row["50MA"]        / 100 * w["50MA"]
        + row["200MA"]       / 100 * w["200MA"]
        + row["RSI>50"]      / 100 * w["RSI>50"]
        + row["WeeklyReturn"]/ 100 * w["WeeklyReturn"],
        2,
    )


def status(e: float) -> str:
    if   e >= 60: return "Strong"
    elif e >= 40: return "Moderate"
    elif e >= 20: return "Weak"
    else:         return "No Edge"


# ── main ─────────────────────────────────────────────────────────────────────

def build_dashboard():
    # Load & normalise sector map
    stocks_df = pd.read_csv(STOCKS_FILE)
    stocks_df["sector"] = (stocks_df["sector"]
                           .str.strip()
                           .replace("Auo Index", "Auto Index"))
    stocks_df["stock"]  = stocks_df["stock"].str.strip()

    tickers = stocks_df["stock"].unique().tolist()
    prices  = fetch_prices(tickers)

    # Per-stock signals
    rows = []
    for _, row in stocks_df.iterrows():
        tk, sec = row["stock"], row["sector"]
        if tk not in prices.columns:
            print(f"  MISSING: {tk}")
            continue
        sig = stock_signals(prices[tk])
        if sig is None:
            print(f"  NO DATA: {tk}")
            continue
        sig.update({"stock": tk, "sector": sec})
        rows.append(sig)

    sig_df = pd.DataFrame(rows)

    # Aggregate per sector
    sector_rows = []
    for sec, grp in sig_df.groupby("sector"):
        n = len(grp)
        sector_rows.append({
            "Sector":       sec,
            "20MA":         round(grp["above_20ma"].sum()              / n * 100, 2),
            "50MA":         round(grp["above_50ma"].sum()              / n * 100, 2),
            "200MA":        round(grp["above_200ma"].sum()             / n * 100, 2),
            "RSI>50":       round(grp["rsi_above_50"].sum()            / n * 100, 2),
            "WeeklyReturn": round(grp["weekly_return_positive"].sum()  / n * 100, 2),
        })

    df = pd.DataFrame(sector_rows)
    df["EdgeScore"]    = df.apply(edge_score, axis=1)
    df                 = df.sort_values("EdgeScore", ascending=False).reset_index(drop=True)
    df["Rank"]         = df.index + 1
    avg                = df["EdgeScore"].mean()
    df["RelativeEdge"] = (df["EdgeScore"] - avg).round(2)
    df["Status"]       = df["EdgeScore"].apply(status)

    df.to_csv(DATAFILE, index=False)
    print(f"Saved {len(df)} sectors → {DATAFILE}")

    # Build HTML
    js_data = json.dumps(
        df.rename(columns={
            "Sector": "sector", "20MA": "p20", "50MA": "p50", "200MA": "p200",
            "RSI>50": "prsi", "WeeklyReturn": "pweek",
            "EdgeScore": "edge", "Rank": "rank",
            "RelativeEdge": "relative", "Status": "status",
        }).to_dict(orient="records"),
        indent=2,
    )
    html    = TEMPLATE.read_text()
    start   = html.find("const dashboardData =")
    end     = html.find("];", start)
    OUTPUT.write_text(html[:start] + "const dashboardData = " + js_data + html[end + 2:])
    print(f"Dashboard written → {OUTPUT}")


if __name__ == "__main__":
    build_dashboard()
