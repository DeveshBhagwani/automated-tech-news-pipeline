import json
import gspread
from google.oauth2.service_account import Credentials

# ── CONFIG ────────────────────────────────────────────────────────────────────
CREDENTIALS_FILE = "credentials.json"
SPREADSHEET_ID   = "1qrCNCVH0EfHh9D3cJTlSKZ_sK6065ICLjG7rt1BefLU"   
SHEET_NAME       = "Sheet1"                     
INPUT_FILE       = "summarized_articles.json"

# Scopes required for read/write access to Sheets and Drive
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ── HEADER ROW ────────────────────────────────────────────────────────────────
HEADERS = ["Title", "Author", "Date", "URL", "Summary", "Tags"]

# ── AUTH ──────────────────────────────────────────────────────────────────────

def get_sheet(spreadsheet_id: str, sheet_name: str):
    """
    Authenticate with the service account and return the target worksheet.
    """
    creds  = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)

    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet   = spreadsheet.worksheet(sheet_name)
    return worksheet


# ── HEADER SETUP ──────────────────────────────────────────────────────────────

def ensure_headers(worksheet) -> None:
    """
    Check if row 1 already has our headers.
    If the sheet is empty or headers differ, write them now.
    This makes the function idempotent — safe to call on every run.
    """
    existing = worksheet.row_values(1)

    if existing == HEADERS:
        print("[INFO] Headers already present — skipping header write.")
        return

    print("[INFO] Writing header row...")
    worksheet.update("A1", [HEADERS])

    # Style the header row: bold + light blue background
    worksheet.format("A1:F1", {
        "textFormat":      {"bold": True, "fontSize": 11},
        "backgroundColor": {"red": 0.678, "green": 0.847, "blue": 0.902},
        "horizontalAlignment": "CENTER"
    })
    print("[INFO] Header row written and formatted.")


# ── DEDUPLICATION ─────────────────────────────────────────────────────────────

def get_existing_titles(worksheet) -> set:
    """
    Fetch all values in column A (Title) to avoid inserting duplicates.
    Returns a set of lowercase title strings for fast lookup.
    """
    titles = worksheet.col_values(1)   # all values in column A
    # Skip the header row itself
    return {t.strip().lower() for t in titles[1:] if t.strip()}


# ── ROW BUILDER ───────────────────────────────────────────────────────────────

def article_to_row(article: dict) -> list:
    """
    Map a summarized article dict to an ordered list matching HEADERS.
    Sanitizes each field to ensure no None values reach the Sheet.
    """
    return [
        str(article.get("title",   "Untitled")).strip(),
        str(article.get("author",  "Unknown")).strip(),
        str(article.get("date",    "1900-01-01")).strip(),
        str(article.get("url",     "")).strip(),
        str(article.get("summary", "")).strip(),
        str(article.get("tags",    "")).strip(),
    ]


# ── BATCH UPLOADER ────────────────────────────────────────────────────────────

def upload_articles(worksheet,
                    articles:   list[dict],
                    existing:   set) -> tuple[int, int]:
    """
    Filter out duplicates and append all new articles in a single
    batch API call — far more efficient than one row at a time.

    Returns (inserted_count, skipped_count).
    """
    new_rows = []
    skipped  = 0

    for article in articles:
        title = str(article.get("title", "")).strip().lower()

        if title in existing:
            print(f"  [SKIP] Duplicate: {article.get('title', '')[:60]}")
            skipped += 1
            continue

        new_rows.append(article_to_row(article))

    if not new_rows:
        print("[INFO] No new articles to insert.")
        return 0, skipped

    # gspread's append_rows sends a single HTTP request for all rows
    worksheet.append_rows(
        new_rows,
        value_input_option="USER_ENTERED",  # lets Sheets parse dates natively
        insert_data_option="INSERT_ROWS",
        table_range="A1"
    )

    return len(new_rows), skipped


# ── COLUMN FORMATTER ──────────────────────────────────────────────────────────

def format_columns(worksheet) -> None:
    """
    Auto-resize columns and set sensible fixed widths for readability.
    Runs after upload so it covers all rows including newly added ones.
    """
    requests_body = {
        "requests": [
            # Title column (A) — wide
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId":    worksheet.id,
                        "dimension":  "COLUMNS",
                        "startIndex": 0,
                        "endIndex":   1
                    },
                    "properties": {"pixelSize": 320},
                    "fields": "pixelSize"
                }
            },
            # Author (B)
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId":    worksheet.id,
                        "dimension":  "COLUMNS",
                        "startIndex": 1,
                        "endIndex":   2
                    },
                    "properties": {"pixelSize": 160},
                    "fields": "pixelSize"
                }
            },
            # Date (C)
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId":    worksheet.id,
                        "dimension":  "COLUMNS",
                        "startIndex": 2,
                        "endIndex":   3
                    },
                    "properties": {"pixelSize": 120},
                    "fields": "pixelSize"
                }
            },
            # URL (D)
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId":    worksheet.id,
                        "dimension":  "COLUMNS",
                        "startIndex": 3,
                        "endIndex":   4
                    },
                    "properties": {"pixelSize": 280},
                    "fields": "pixelSize"
                }
            },
            # Summary (E) — widest
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId":    worksheet.id,
                        "dimension":  "COLUMNS",
                        "startIndex": 4,
                        "endIndex":   5
                    },
                    "properties": {"pixelSize": 420},
                    "fields": "pixelSize"
                }
            },
            # Tags (F)
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId":    worksheet.id,
                        "dimension":  "COLUMNS",
                        "startIndex": 5,
                        "endIndex":   6
                    },
                    "properties": {"pixelSize": 200},
                    "fields": "pixelSize"
                }
            },
        ]
    }

    worksheet.spreadsheet.batch_update(requests_body)
    print("[INFO] Column widths formatted.")


# ── MAIN PIPELINE ─────────────────────────────────────────────────────────────

def run_upload(input_file:      str = INPUT_FILE,
               spreadsheet_id:  str = SPREADSHEET_ID,
               sheet_name:      str = SHEET_NAME) -> None:
    """
    Full upload pipeline:
      1. Authenticate
      2. Ensure headers exist
      3. Load summarized articles
      4. Deduplicate against existing sheet data
      5. Batch append new rows
      6. Format columns
    """

    # ── Step 1: Authenticate ──────────────────────────────────────────────────
    print("[INFO] Authenticating with Google Sheets API...")
    try:
        worksheet = get_sheet(spreadsheet_id, sheet_name)
        print(f"[INFO] Connected to sheet: '{worksheet.title}'")
    except FileNotFoundError:
        print(f"[ERROR] '{CREDENTIALS_FILE}' not found in project folder.")
        return
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"[ERROR] Spreadsheet ID '{spreadsheet_id}' not found.")
        print(f"        Check SPREADSHEET_ID in the config and that you shared")
        print(f"        the sheet with your service account email.")
        return
    except Exception as e:
        print(f"[ERROR] Authentication failed: {e}")
        return

    # ── Step 2: Ensure headers ────────────────────────────────────────────────
    ensure_headers(worksheet)

    # ── Step 3: Load articles ─────────────────────────────────────────────────
    print(f"[INFO] Loading articles from '{input_file}'...")
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            articles: list[dict] = json.load(f)
        print(f"[INFO] {len(articles)} articles loaded.")
    except FileNotFoundError:
        print(f"[ERROR] '{input_file}' not found. Run summarizer.py first.")
        return

    # ── Step 4: Deduplicate ───────────────────────────────────────────────────
    print("[INFO] Checking for existing records in sheet...")
    existing_titles = get_existing_titles(worksheet)
    print(f"[INFO] {len(existing_titles)} existing titles found in sheet.")

    # ── Step 5: Upload ────────────────────────────────────────────────────────
    print("[INFO] Uploading new articles...")
    inserted, skipped = upload_articles(worksheet, articles, existing_titles)

    # ── Step 6: Format ────────────────────────────────────────────────────────
    if inserted > 0:
        format_columns(worksheet)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n[DONE] Upload complete.")
    print(f"  ✓ Inserted : {inserted} new rows")
    print(f"  ✓ Skipped  : {skipped} duplicates")
    print(f"  ✓ Sheet URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_upload()
