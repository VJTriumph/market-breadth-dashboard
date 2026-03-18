import json
import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).parent
STOCKS_FILE = BASE / "data" / "stocks.csv"
DATAFILE    = BASE / "data" / "dashboard.csv"
STOCKS_DATA_FILE = BASE / "data" / "stocks_data.csv"
QUALITY_FILE= BASE / "data" / "data_quality.json"
TEMPLATE    = BASE / "market_breadth_dashboard.html"
OUTPUT      = BASE / "output" / "market_breadth_dashboard_output.html"

MA_PERIODS   = [20, 50, 200]
RSI_PERIOD   = 14
HISTORY_DAYS = 450   # enough for 200-day SMA + RSI warmup

# ── helpers ────────────────────────────────────────────────────────────────────

def compute_rsi(series, period=14):
    """Simple SMA RSI (no smoothing) - plain avg gain/loss over last N bars."""
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs       = avg_gain / avg_loss.replace(0, float('nan'))
    return 100 - (100 / (1 + rs))

def fetch_prices(tickers):
    import numpy as np
    ns    = [t + ".NS" for t in tickers]
    end   = datetime.today() + timedelta(days=1)
    start = end - timedelta(days=HISTORY_DAYS)
    print(f"Fetching {len(ns)} tickers ...")
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

def stock_signals(s):
    import numpy as np
    from datetime import timedelta
    s = s.dropna()
    if len(s) < 10:
        return None
    last      = s.iloc[-1]
    last_date = s.index[-1]
    sigs = {}

    for ma in MA_PERIODS:
        if len(s) >= ma:
            ma_val = s.rolling(ma).mean().iloc[-1]
            sigs[f"above_{ma}ma"]    = 1 if last > ma_val else 0
            sigs[f"ma{ma}_value"]    = round(float(ma_val), 4)
        else:
            sigs[f"above_{ma}ma"]    = 0
            sigs[f"ma{ma}_value"]    = None

    if len(s) >= RSI_PERIOD + 1:
        rsi_series = compute_rsi(s, RSI_PERIOD)
        rsi        = rsi_series.iloc[-1]
        sigs["rsi_value"]      = round(float(rsi), 4) if not np.isnan(rsi) else None
        sigs["rsi_above_50"]   = 1 if (not np.isnan(rsi) and rsi > 50) else 0
    else:
        sigs["rsi_value"]      = None
        sigs["rsi_above_50"]   = 0

    # Weekly return: compare vs close 5 trading days ago (one week back)
    if len(s) >= 6:
        prev_close             = s.iloc[-6]
        weekly_ret             = (last / prev_close - 1) * 100 if prev_close != 0 else 0
        sigs["prev_close_5d"]  = round(float(prev_close), 4)
        sigs["last_close"]     = round(float(last), 4)
        sigs["weekly_return_pct"] = round(float(weekly_ret), 4)
        sigs["weekly_return_positive"] = 1 if weekly_ret > 0 else 0
    else:
        sigs["prev_close_5d"]  = None
        sigs["last_close"]     = round(float(last), 4)
        sigs["weekly_return_pct"] = None
        sigs["weekly_return_positive"] = 0

    sigs["last_date"] = str(last_date.date())
    return sigs

def edge_score(row):
    w = {"20MA": 15, "50MA": 20, "200MA": 25, "RSI>50": 20, "WeeklyReturn": 20}
    return round(
        row["20MA"]          / 100 * w["20MA"] +
        row["50MA"]          / 100 * w["50MA"] +
        row["200MA"]         / 100 * w["200MA"] +
        row["RSI>50"]        / 100 * w["RSI>50"] +
        row["WeeklyReturn"]  / 100 * w["WeeklyReturn"],
        2,
    )

def status(e):
    if e >= 60: return "Strong"
    elif e >= 40: return "Moderate"
    elif e >= 20: return "Weak"
    else:         return "No Edge"

def build_dashboard():
    run_time  = datetime.now()
    stocks_df = pd.read_csv(STOCKS_FILE)
    stocks_df["sector"] = (stocks_df["sector"]
                           .str.strip()
                           .replace("Auo Index", "Auto Index"))
    stocks_df["stock"]  = stocks_df["stock"].str.strip()

    tickers = stocks_df["stock"].unique().tolist()
    prices  = fetch_prices(tickers)

    rows             = []
    missing_tickers  = []
    nodata_tickers   = []
    stale_tickers    = []
    ok_tickers       = []

    if not prices.empty:
        most_recent_date = prices.dropna(how="all").index[-1].date()
    else:
        most_recent_date = run_time.date()

    stale_threshold = most_recent_date - timedelta(days=7)

    for _, row in stocks_df.iterrows():
        tk, sec = row["stock"], row["sector"]
        if tk not in prices.columns:
            print(f"  MISSING : {tk}")
            missing_tickers.append({"stock": tk, "sector": sec, "reason": "Not in yfinance response"})
            continue

        sig = stock_signals(prices[tk])
        if sig is None:
            print(f"  NO DATA : {tk}")
            nodata_tickers.append({"stock": tk, "sector": sec, "reason": "Insufficient bars (<10)"})
            continue

        last_date_str = sig.get("last_date", None)
        if last_date_str:
            from datetime import date as date_cls
            ld = date_cls.fromisoformat(last_date_str)
            if ld < stale_threshold:
                stale_tickers.append({
                    "stock": tk, "sector": sec,
                    "last_date": last_date_str,
                    "days_behind": (most_recent_date - ld).days
                })
                print(f"  STALE   : {tk} last={last_date_str}")

        ok_tickers.append(tk)
        sig.update({"stock": tk, "sector": sec})
        rows.append(sig)

    sig_df = pd.DataFrame(rows)

    # ── Save per-stock detail CSV ─────────────────────────────────────────────
    stock_detail_cols = [
        "sector", "stock", "last_date", "last_close",
        "ma20_value", "above_20ma",
        "ma50_value", "above_50ma",
        "ma200_value", "above_200ma",
        "rsi_value", "rsi_above_50",
        "prev_close_5d", "weekly_return_pct", "weekly_return_positive",
    ]
    available_cols = [c for c in stock_detail_cols if c in sig_df.columns]
    stocks_out = sig_df[available_cols].sort_values(["sector", "stock"]).reset_index(drop=True)
    stocks_out.to_csv(STOCKS_DATA_FILE, index=False)
    print(f"Saved per-stock data -> {STOCKS_DATA_FILE}")

    # ── Aggregate by sector ───────────────────────────────────────────────────
    sector_rows  = []
    sector_counts = {}
    for sec, grp in sig_df.groupby("sector"):
        n = len(grp)
        total_in_sector = len(stocks_df[stocks_df["sector"] == sec])
        sector_counts[sec] = {"ok": n, "total": total_in_sector}
        sector_rows.append({
            "Sector":       sec,
            "20MA":         round(grp["above_20ma"].sum()              / total_in_sector * 100, 2),
            "50MA":         round(grp["above_50ma"].sum()              / total_in_sector * 100, 2),
            "200MA":        round(grp["above_200ma"].sum()             / total_in_sector * 100, 2),
            "RSI>50":       round(grp["rsi_above_50"].sum()            / total_in_sector * 100, 2),
            "WeeklyReturn": round(grp["weekly_return_positive"].sum()  / total_in_sector * 100, 2),
            "StocksOK":     n,
            "StocksTotal":  total_in_sector,
        })

    df = pd.DataFrame(sector_rows)
    df["EdgeScore"]    = df.apply(edge_score, axis=1)
    df                 = df.sort_values("EdgeScore", ascending=False).reset_index(drop=True)
    df["Rank"]         = df.index + 1
    avg                = df["EdgeScore"].mean()
    df["RelativeEdge"] = (df["EdgeScore"] - avg).round(2)
    df["Status"]       = df["EdgeScore"].apply(status)
    df["DataWarning"]  = df.apply(
        lambda r: "WARNING" if r["StocksOK"] < r["StocksTotal"] else "OK",
        axis=1
    )

    df.to_csv(DATAFILE, index=False)
    print(f"Saved {len(df)} sectors -> {DATAFILE}")

    quality = {
        "run_time":        run_time.strftime("%Y-%m-%d %H:%M IST"),
        "most_recent_bar": str(most_recent_date),
        "total_stocks":    len(tickers),
        "ok_stocks":       len(ok_tickers),
        "missing_count":   len(missing_tickers),
        "nodata_count":    len(nodata_tickers),
        "stale_count":     len(stale_tickers),
        "missing":         missing_tickers,
        "nodata":          nodata_tickers,
        "stale":           stale_tickers,
        "sector_counts":   sector_counts,
    }
    QUALITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUALITY_FILE.write_text(json.dumps(quality, indent=2))
    print(f"Quality report -> {QUALITY_FILE}")
    print(f"  OK={len(ok_tickers)} Missing={len(missing_tickers)} NoData={len(nodata_tickers)} Stale={len(stale_tickers)}")
    if missing_tickers:
        print("  MISSING STOCKS:", [t["stock"] for t in missing_tickers])
    if stale_tickers:
        print("  STALE STOCKS:", [t["stock"] + "(" + t["last_date"] + ")" for t in stale_tickers])

    js_data = json.dumps(
        df.rename(columns={
            "Sector":       "sector",
            "20MA":         "p20",
            "50MA":         "p50",
            "200MA":        "p200",
            "RSI>50":       "prsi",
            "WeeklyReturn": "pweek",
            "EdgeScore":    "edge",
            "Rank":         "rank",
            "RelativeEdge": "relative",
            "Status":       "status",
            "StocksOK":     "stocks_ok",
            "StocksTotal":  "stocks_total",
            "DataWarning":  "data_warning",
        }).to_dict(orient="records"),
        indent=2,
    )
    quality_js = json.dumps(quality, indent=2)

    html  = TEMPLATE.read_text()
    start = html.find("const dashboardData =")
    end   = html.find("];", start)
    html  = html[:start] + "const dashboardData = " + js_data + html[end + 2:]

    quality_marker = "const qualityData ="
    if quality_marker in html:
        qs   = html.find(quality_marker)
        qe   = html.find("};", qs)
        html = html[:qs] + quality_marker + " " + quality_js + html[qe + 2:]
    else:
        insert_after = "const dashboardData = " + js_data
        html = html.replace(
            insert_after,
            insert_after + "\nconst qualityData = " + quality_js + ";"
        )

    OUTPUT.write_text(html)
    print(f"Dashboard written -> {OUTPUT}")

if __name__ == "__main__":
    build_dashboard()
