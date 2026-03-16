import json
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).parent
STOCKS_FILE = BASE_DIR / "data" / "stocks.csv"
DASHBOARD_FILE = BASE_DIR / "data" / "dashboard.csv"
HTML_TEMPLATE = BASE_DIR / "market_breadth_dashboard.html"
OUTPUT_HTML = BASE_DIR / "output" / "market_breadth_dashboard_output.html"


def create_sample_dashboard():
    stocks_df = pd.read_csv(STOCKS_FILE)

    # Sample demo output for now
    # Later this will be replaced with real calculations
    unique_sectors = stocks_df["Sector"].dropna().unique().tolist()

    rows = []
    for i, sector in enumerate(unique_sectors, start=1):
        rows.append({
            "Sector": sector,
            "20MA": 40 + i,
            "50MA": 45 + i,
            "200MA": 50 + i,
            "RSI>50": 35 + i,
            "WeeklyReturn": 30 + i,
            "EdgeScore": 40 + i * 2,
            "Rank": i,
            "RelativeEdge": round((40 + i * 2) - 50, 2),
            "Status": "Strong" if (40 + i * 2) >= 55 else "Moderate" if (40 + i * 2) >= 40 else "Weak"
        })

    df = pd.DataFrame(rows)
    df.to_csv(DASHBOARD_FILE, index=False)
    return df


def build_html_from_csv():
    df = pd.read_csv(DASHBOARD_FILE)

    df = df.rename(columns={
        "Sector": "sector",
        "20MA": "p20",
        "50MA": "p50",
        "200MA": "p200",
        "RSI>50": "prsi",
        "WeeklyReturn": "pweek",
        "EdgeScore": "edge",
        "Rank": "rank",
        "RelativeEdge": "relative",
        "Status": "status"
    })

    dashboard_json = json.dumps(
        df.to_dict(orient="records"),
        ensure_ascii=False,
        indent=2
    )

    html = HTML_TEMPLATE.read_text(encoding="utf-8")

    start_marker = "const dashboardData = ["
    end_marker = "];"

    start_idx = html.find(start_marker)
    if start_idx == -1:
        raise ValueError("dashboardData block not found in HTML")

    end_idx = html.find(end_marker, start_idx)
    if end_idx == -1:
        raise ValueError("End of dashboardData block not found in HTML")

    replacement = f"const dashboardData = {dashboard_json}"
    new_html = html[:start_idx] + replacement + html[end_idx + len(end_marker):]

    OUTPUT_HTML.write_text(new_html, encoding="utf-8")
    print(f"Dashboard created: {OUTPUT_HTML}")


if __name__ == "__main__":
    create_sample_dashboard()
    build_html_from_csv()
