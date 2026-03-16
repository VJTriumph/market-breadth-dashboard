# build_dashboard.py
# Main script to fetch market breadth data and generate the dashboard

import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from jinja2 import Template
import os
from datetime import datetime

# Paths
DATA_DIR = "data"
OUTPUT_DIR = "output"
STOCKS_CSV = os.path.join(DATA_DIR, "stocks.csv")
DASHBOARD_CSV = os.path.join(DATA_DIR, "dashboard.csv")
TEMPLATE_HTML = "market_breadth_dashboard.html"
OUTPUT_HTML = os.path.join(OUTPUT_DIR, "market_breadth_dashboard_output.html")

def load_stocks():
      """Load stock list from CSV."""
      df = pd.read_csv(STOCKS_CSV)
      return df["ticker"].tolist()

def fetch_market_breadth(tickers):
      """Fetch price data and compute market breadth metrics."""
      data = yf.download(tickers, period="1y", auto_adjust=True, progress=False)["Close"]
      results = []
      for ticker in tickers:
                if ticker not in data.columns:
                              continue
                          prices = data[ticker].dropna()
                if len(prices) < 200:
                              continue
                          ma50 = prices.rolling(50).mean().iloc[-1]
                ma200 = prices.rolling(200).mean().iloc[-1]
                current = prices.iloc[-1]
                results.append({
                    "ticker": ticker,
                    "price": round(current, 2),
                    "ma50": round(ma50, 2),
                    "ma200": round(ma200, 2),
                    "above_ma50": current > ma50,
                    "above_ma200": current > ma200,
                })
            return pd.DataFrame(results)

def save_dashboard_csv(df):
      """Save computed metrics to dashboard.csv."""
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(DASHBOARD_CSV, index=False)

def build_html(df):
      """Render HTML dashboard from template."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pct_above_ma50 = round(df["above_ma50"].mean() * 100, 1)
    pct_above_ma200 = round(df["above_ma200"].mean() * 100, 1)
    updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    with open(TEMPLATE_HTML, "r") as f:
              template = Template(f.read())

    html = template.render(
              pct_above_ma50=pct_above_ma50,
              pct_above_ma200=pct_above_ma200,
              updated=updated,
              stocks=df.to_dict(orient="records"),
    )

    with open(OUTPUT_HTML, "w") as f:
              f.write(html)
          print(f"Dashboard written to {OUTPUT_HTML}")

if __name__ == "__main__":
      tickers = load_stocks()
    df = fetch_market_breadth(tickers)
    save_dashboard_csv(df)
    build_html(df)
