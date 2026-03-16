import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).parent
STOCKS_FILE = BASE_DIR / "data" / "stocks.csv"
DASHBOARD_FILE = BASE_DIR / "data" / "dashboard.csv"
HTML_TEMPLATE = BASE_DIR / "market_breadth_dashboard.html"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_HTML = OUTPUT_DIR / "market_breadth_dashboard_output.html"


def create_sample_dashboard():
    stocks_df = pd.read_csv(STOCKS_FILE)
        # Support both 'sector' (lowercase) and 'Sector' (uppercase) column names
            col_map = {c.lower(): c for c in stocks_df.columns}
                sector_col = col_map.get("sector", "sector")
                    sectors = stocks_df[sector_col].dropna().unique().tolist()

                        rows = []
                            for i, sector in enumerate(sectors, start=1):
                                    edge = round(35 + i * 2.5, 2)
                                            rows.append({
                                                        "Sector": sector,
                                                                    "20MA": round(30 + i * 2, 2),
                                                                                "50MA": round(35 + i * 2, 2),
                                                                                            "200MA": round(40 + i * 2, 2),
                                                                                                        "RSI>50": round(25 + i * 2, 2),
                                                                                                                    "WeeklyReturn": round(20 + i * 2, 2),
                                                                                                                                "EdgeScore": edge,
                                                                                                                                            "Rank": i,
                                                                                                                                                        "RelativeEdge": 0.0,  # filled below
                                                                                                                                                                    "Status": "Strong" if edge >= 55 else "Moderate" if edge >= 40 else "Weak"
                                                                                                                                                                            })

                                                                                                                                                                                df = pd.DataFrame(rows)
                                                                                                                                                                                    avg_edge = df["EdgeScore"].mean()
                                                                                                                                                                                        df["RelativeEdge"] = (df["EdgeScore"] - avg_edge).round(2)

                                                                                                                                                                                            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
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

                                                                                                                                                                                                                                                                                                                                    # Generate last updated timestamp (IST = UTC+5:30)
                                                                                                                                                                                                                                                                                                                                        now_utc = datetime.now(timezone.utc)
                                                                                                                                                                                                                                                                                                                                            last_updated = now_utc.strftime("%d %b %Y %I:%M %p UTC")

                                                                                                                                                                                                                                                                                                                                                html = HTML_TEMPLATE.read_text(encoding="utf-8")

                                                                                                                                                                                                                                                                                                                                                    # Replace dashboardData block
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

                                                                                                                                                                                                                                                                                                                                                                                                        # Replace lastUpdated placeholder
                                                                                                                                                                                                                                                                                                                                                                                                            new_html = new_html.replace("LAST_UPDATED_PLACEHOLDER", last_updated)

                                                                                                                                                                                                                                                                                                                                                                                                                OUTPUT_HTML.write_text(new_html, encoding="utf-8")
                                                                                                                                                                                                                                                                                                                                                                                                                    print(f"Dashboard created: {OUTPUT_HTML}")
                                                                                                                                                                                                                                                                                                                                                                                                                        print(f"Last updated: {last_updated}")


                                                                                                                                                                                                                                                                                                                                                                                                                        if __name__ == "__main__":
                                                                                                                                                                                                                                                                                                                                                                                                                            create_sample_dashboard()
                                                                                                                                                                                                                                                                                                                                                                                                                                build_html_from_csv()