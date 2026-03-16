import os
import json
from pathlib import Path

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# =========================
# SETTINGS
# =========================
SPREADSHEET_NAME = "Sector Breadth Dashboard"
DASHBOARD_SHEET  = "Dashboard"

BASE_DIR    = Path(__file__).parent
HTML_TEMPLATE = BASE_DIR / "market_breadth_dashboard.html"
OUTPUT_HTML   = BASE_DIR / "output" / "market_breadth_dashboard_output.html"

# =========================
# GOOGLE SHEETS AUTH
# =========================
def get_gsheet_client():
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds_json:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON secret not found")
    creds_dict = json.loads(creds_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

# =========================
# READ DASHBOARD SHEET
# =========================
def read_dashboard_from_gsheet() -> pd.DataFrame:
    """
    Reads the Dashboard sheet which has columns:
    Sector | 20MA | 50MA | 200MA | RSI>50 | X% | EdgeScore | Rank | RelativeEdge | Status
    """
    gc = get_gsheet_client()
    sh = gc.open(SPREADSHEET_NAME)
    ws = sh.worksheet(DASHBOARD_SHEET)
    values = ws.get_all_values()
    if not values or len(values) < 2:
        raise ValueError("Dashboard sheet is empty or has no data rows")
    df = pd.DataFrame(values[1:], columns=values[0])
    return df

# =========================
# TRANSFORM TO HTML FIELDS
# =========================
def transform_for_html(df: pd.DataFrame) -> list:
    """
    Maps Google Sheet column names -> HTML template field names:
      Sector       -> sector
      20MA         -> p20
      50MA         -> p50
      200MA        -> p200
      RSI>50       -> prsi
      X%           -> pweek
      EdgeScore    -> edge
      Rank         -> rank
      RelativeEdge -> relative
      Status       -> status
    Returns a list of dicts ready for JSON injection.
    """
    col_map = {
        "Sector":       "sector",
        "20MA":         "p20",
        "50MA":         "p50",
        "200MA":        "p200",
        "RSI>50":       "prsi",
        "X%":           "pweek",
        "EdgeScore":    "edge",
        "Rank":         "rank",
        "RelativeEdge": "relative",
        "Status":       "status",
    }

    def safe_float(val):
        try:
            return round(float(val), 2)
        except (ValueError, TypeError):
            return 0.0

    records = []
    for _, row in df.iterrows():
        record = {}
        for sheet_col, html_key in col_map.items():
            raw = row.get(sheet_col, "")
            if html_key in ("sector", "status"):
                record[html_key] = str(raw).strip()
            else:
                record[html_key] = safe_float(raw)
        # Only include rows that have a sector name
        if record.get("sector"):
            records.append(record)
    return records

# =========================
# RENDER HTML
# =========================
def render_html(records: list):
    html = HTML_TEMPLATE.read_text(encoding="utf-8")

    dashboard_json = json.dumps(records, ensure_ascii=False, indent=2)

    start_marker = "const dashboardData = ["
    end_marker   = "];"

    start_idx = html.find(start_marker)
    if start_idx == -1:
        raise ValueError("'const dashboardData = [' marker not found in HTML template")

    end_idx = html.find(end_marker, start_idx)
    if end_idx == -1:
        raise ValueError("End marker '};' not found after dashboardData")

    replacement = f"const dashboardData = {dashboard_json}"
    new_html = html[:start_idx] + replacement + html[end_idx + len(end_marker):]

    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(new_html, encoding="utf-8")
    print(f"Dashboard written to {OUTPUT_HTML} ({len(records)} sectors)")

# =========================
# MAIN
# =========================
def main():
    print("Reading Dashboard sheet from Google Sheets...")
    df = read_dashboard_from_gsheet()
    print(f"  Got {len(df)} rows, columns: {df.columns.tolist()}")
    records = transform_for_html(df)
    print(f"  Transformed {len(records)} sector records")
    render_html(records)
    print("Done.")

if __name__ == "__main__":
    main()
