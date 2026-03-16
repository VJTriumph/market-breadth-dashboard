import json
import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent

TEMPLATE = BASE / "market_breadth_dashboard.html"
DATAFILE = BASE / "data" / "dashboard.csv"
OUTPUT = BASE / "output" / "market_breadth_dashboard_output.html"


def build_dashboard():

    df = pd.read_csv(DATAFILE)

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
        indent=2
    )

    html = TEMPLATE.read_text()

    start = html.find("const dashboardData =")
    end = html.find("];", start)

    new_html = (
        html[:start] +
        "const dashboardData = " + dashboard_json +
        html[end + 2:]
    )

    OUTPUT.write_text(new_html)

    print("Dashboard created:", OUTPUT)


if __name__ == "__main__":
    build_dashboard()
