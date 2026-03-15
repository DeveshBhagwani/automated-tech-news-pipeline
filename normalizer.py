import json
import re
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from dateutil.parser import ParserError
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
INPUT_FILE  = "raw_articles.json"
OUTPUT_FILE = "cleaned_articles.json"

# ── HTML CLEANING ─────────────────────────────────────────────────────────────

def strip_html(raw_html: str) -> str:
    """
    Remove all HTML tags and decode entities.
    Preserves natural sentence spacing by replacing block-level
    tags with a newline before stripping.
    """
    if not raw_html or not raw_html.strip():
        return ""

    soup = BeautifulSoup(raw_html, "lxml")

    # Insert a newline after every block-level tag so words don't merge
    BLOCK_TAGS = ["p", "li", "h1", "h2", "h3", "h4", "h5", "h6",
                  "div", "blockquote", "pre", "tr"]
    for tag in soup.find_all(BLOCK_TAGS):
        tag.insert_after("\n")

    # Remove non-content elements entirely
    for junk in soup.find_all(["script", "style", "figure", "img",
                                "iframe", "nav", "aside"]):
        junk.decompose()

    raw_text = soup.get_text(separator=" ")
    return _clean_whitespace(raw_text)


def _clean_whitespace(text: str) -> str:
    """
    Collapse multiple spaces/newlines into single spaces,
    and strip leading/trailing whitespace.
    """
    # Replace newlines and tabs with a space
    text = text.replace("\n", " ").replace("\t", " ")
    # Collapse runs of whitespace
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


# ── DATE NORMALIZATION ────────────────────────────────────────────────────────

# Ordered list of explicit format patterns to try before falling back
# to dateutil (handles ambiguous strings more predictably).
_DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%SZ",      # ISO 8601 UTC  → 2024-05-10T14:22:00Z
    "%Y-%m-%dT%H:%M:%S%z",     # ISO 8601 TZ   → 2024-05-10T14:22:00+00:00
    "%Y-%m-%d",                 # Plain date    → 2024-05-10
    "%B %d, %Y",                # Long month    → May 10, 2024
    "%b %d, %Y",                # Short month   → May 10, 2024
    "%d %B %Y",                 # Day first     → 10 May 2024
    "%d-%m-%Y",                 # Euro numeric  → 10-05-2024
    "%m/%d/%Y",                 # US numeric    → 05/10/2024
    "%d/%m/%Y",                 # UK numeric    → 10/05/2024
]


def normalize_date(raw_date: str) -> str:
    """
    Convert any recognizable date string into YYYY-MM-DD.
    Returns "1900-01-01" as a sentinel value if parsing fails,
    so downstream processes can easily filter bad rows.
    """
    if not raw_date or raw_date.strip().lower() in ("unknown", "n/a", ""):
        return "1900-01-01"

    raw_date = raw_date.strip()

    # 1️⃣  Try each explicit format first (fast, unambiguous)
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(raw_date, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # 2️⃣  Fall back to dateutil for natural-language / edge-case strings
    try:
        dt = date_parser.parse(raw_date, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except (ParserError, OverflowError, ValueError):
        print(f"  [WARN] Could not parse date: '{raw_date}' → using sentinel 1900-01-01")
        return "1900-01-01"


# ── FIELD VALIDATION ──────────────────────────────────────────────────────────

def validate_record(record: dict) -> dict:
    """
    Ensure every expected key exists and holds a non-empty string.
    Fills missing/null fields with sensible defaults so the pipeline
    never crashes on a malformed record.
    """
    defaults = {
        "title":   "Untitled",
        "author":  "Unknown",
        "date":    "1900-01-01",
        "url":     "",
        "content": "",
    }
    for key, fallback in defaults.items():
        if not record.get(key) or not str(record[key]).strip():
            record[key] = fallback

    return record


# ── MAIN NORMALIZER ───────────────────────────────────────────────────────────

def normalize_articles(input_file: str = INPUT_FILE,
                        output_file: str = OUTPUT_FILE) -> list[dict]:
    """
    Full normalization pipeline:
      1. Load raw JSON
      2. Clean HTML content
      3. Normalize dates
      4. Validate all fields
      5. Save cleaned JSON
    """

    # ── Load ──────────────────────────────────────────────────────────────────
    print(f"[INFO] Loading raw articles from '{input_file}'...")
    with open(input_file, "r", encoding="utf-8") as f:
        raw_articles: list[dict] = json.load(f)
    print(f"[INFO] {len(raw_articles)} articles loaded.")

    cleaned_articles = []
    skipped = 0

    for idx, article in enumerate(raw_articles, start=1):
        print(f"  [{idx}/{len(raw_articles)}] Normalizing: {article.get('title', 'N/A')[:60]}...")

        # ── Step 1: Clean HTML content ────────────────────────────────────────
        raw_content = article.get("content") or ""
        clean_content = strip_html(raw_content)

        # Skip articles with no recoverable content
        if not clean_content:
            print(f"    [SKIP] Empty content after HTML stripping.")
            skipped += 1
            continue

        # ── Step 2: Normalize date ────────────────────────────────────────────
        raw_date = article.get("raw_date") or article.get("date") or ""
        normalized_date = normalize_date(raw_date)

        # ── Step 3: Assemble cleaned record ──────────────────────────────────
        cleaned_record = {
            "title":   article.get("title", "Untitled").strip(),
            "author":  article.get("author", "Unknown").strip(),
            "date":    normalized_date,
            "url":     article.get("url", "").strip(),
            "content": clean_content,
        }

        # ── Step 4: Validate all fields ───────────────────────────────────────
        cleaned_record = validate_record(cleaned_record)
        cleaned_articles.append(cleaned_record)

    # ── Save ──────────────────────────────────────────────────────────────────
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(cleaned_articles, f, indent=2, ensure_ascii=False)

    print(f"\n[DONE] Normalized {len(cleaned_articles)} articles "
          f"({skipped} skipped). Saved to '{output_file}'.")

    return cleaned_articles


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = normalize_articles()

    # ── Sanity preview ────────────────────────────────────────────────────────
    print("\n── SAMPLE CLEANED RECORD ──────────────────────────────────────")
    if results:
        s = results[0]
        print(f"  Title   : {s['title']}")
        print(f"  Author  : {s['author']}")
        print(f"  Date    : {s['date']}")
        print(f"  URL     : {s['url']}")
        print(f"  Content : {s['content'][:200]}...")
