# 🗞️ Automated Tech-News-to-Google-Sheets Pipeline

> A fully local, zero-cost ETL pipeline that scrapes tech articles, cleans and normalizes the data, summarizes each article using a local LLM, and pushes the structured results directly into Google Sheets — automatically.

**Built by [@DeveshBhagwani](https://github.com/DeveshBhagwani)**

---

## 📐 ETL Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EXTRACT (Phase 1)                            │
│                                                                     │
│   dev.to/t/webdev?page=1..3                                         │
│          │                                                          │
│   scraper.py  ──►  requests + BeautifulSoup                         │
│          │         • Paginates through 3 archive pages              │
│          │         • Extracts: title, author, date, content         │
│          ▼                                                          │
│   raw_articles.json                                                 │
└────────────────────────────┬────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│                       TRANSFORM (Phases 2 & 3)                      │
│                                                                     │
│   normalizer.py                                                     │
│          │  • Strips all HTML tags from content                     │
│          │  • Normalizes all dates → YYYY-MM-DD                     │
│          │  • Validates and fills missing fields                    │
│          ▼                                                          │
│   cleaned_articles.json                                             │
│          │                                                          │
│   summarizer.py  ──►  Ollama (llama3.2) on localhost:11434          │
│          │  • Sends article title + content to local LLM            │
│          │  • Receives: 50-word summary + 3 category tags           │
│          │  • JSON repair for truncated responses                   │
│          ▼                                                          │
│   summarized_articles.json                                          │
└────────────────────────────┬────────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────────┐
│                         LOAD (Phase 4)                              │
│                                                                     │
│   sheets_uploader.py  ──►  gspread + Google Sheets API              │
│          │  • Authenticates via Service Account (credentials.json)  │
│          │  • Writes header row with formatting                     │
│          │  • Deduplicates against existing rows                    │
│          │  • Batch-appends all new rows in one API call            │
│          ▼                                                          │
│   ✅ Google Sheets  [ Title | Author | Date | URL | Summary | Tags ]│
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
Automated Tech-News-to-Google-Sheets Pipeline/
│
├── scraper.py               # Pagination scraper
├── normalizer.py            # HTML cleaner & date normalizer
├── summarizer.py            # Local LLM summarization (Ollama)
├── sheets_uploader.py       # Google Sheets integration
│
├── credentials.json         # Google Service Account key
│
├── raw_articles.json        # raw scraped data
├── cleaned_articles.json    # normalized data
├── summarized_articles.json # LLM-enriched data
│
└── README.md
```



---

## 🛠️ Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.10+ | Runtime |
| Ollama | Latest | Local LLM runner |
| llama3.2 | — | Summarization model (~2GB) |
| Google Cloud account | — | Sheets API access |

---

## ⚙️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/DeveshBhagwani/automated-tech-news-pipeline.git
cd automated-tech-news-pipeline
```

### 2. Install Python dependencies

```bash
pip install requests beautifulsoup4 lxml python-dateutil ollama gspread google-auth
```

### 3. Install Ollama and pull the model

Download Ollama from **https://ollama.com/download**, then:

```bash
ollama pull llama3.2
```

Ollama runs automatically in the background after installation. Verify it's active:

```bash
curl http://localhost:11434/api/tags
```

---

## 🔑 Google API Credentials Setup

This is a one-time setup. Follow each step carefully.

### Step 1 — Create a Google Cloud Project

1. Go to **https://console.cloud.google.com**
2. Click **"Select a project"** → **"New Project"**
3. Name it `tech-news-pipeline` → **Create**

### Step 2 — Enable required APIs

Search for and enable both of these APIs in your project:

- **Google Sheets API**
- **Google Drive API**

### Step 3 — Create a Service Account

1. Go to **"IAM & Admin"** → **"Service Accounts"**
2. Click **"Create Service Account"**
3. Name: `tech-news-bot` → **Create and Continue** → **Done**

### Step 4 — Download credentials

1. Click your new service account → **"Keys"** tab
2. **"Add Key"** → **"Create new key"** → **JSON** → **Create**
3. Rename the downloaded file to `credentials.json`
4. Move it into the project root folder

### Step 5 — Create and share the Google Sheet

1. Go to **https://sheets.google.com** → create a **Blank** spreadsheet
2. Name it **`Tech News Pipeline`**
3. Copy the Spreadsheet ID from the URL:
   ```
   https://docs.google.com/spreadsheets/d/YOUR_SPREADSHEET_ID/edit
   ```
4. Open `credentials.json` and find the `"client_email"` field
5. In your Google Sheet → **Share** → paste that email → set role to **Editor** → **Send**

### Step 6 — Configure the uploader

Open `sheets_uploader.py` and paste your Spreadsheet ID:

```python
SPREADSHEET_ID = "YOUR_SPREADSHEET_ID_HERE"
```

### Step 7 — Add credentials.json to .gitignore

```bash
echo "credentials.json" >> .gitignore
echo "*.json" >> .gitignore
```

---

## 🚀 Running the Pipeline

Run each script in order. Each one depends on the output of the previous.

```bash
# Step 1 — Scrape articles (creates raw_articles.json)
python scraper.py

# Step 2 — Clean and normalize (creates cleaned_articles.json)
python normalizer.py

# Step 3 — Summarize with LLM (creates summarized_articles.json)
python summarizer.py

# Step 4 — Push to Google Sheets
python sheets_uploader.py
```

### Expected output after the full run

```
[DONE] Upload complete.
  ✓ Inserted : 45 new rows
  ✓ Skipped  : 0 duplicates
  ✓ Sheet URL: https://docs.google.com/spreadsheets/d/YOUR_ID
```

---

## 📊 Output Schema

Each row written to Google Sheets contains these 6 columns:

| Column | Field | Example |
|--------|-------|---------|
| A | Title | "Why Most React Apps Fail Core Web Vitals" |
| B | Author | "Munna Thakur" |
| C | Date | `2026-03-14` |
| D | URL | `https://dev.to/...` |
| E | Summary | 40–60 word LLM-generated summary |
| F | Tags | `React, Performance, Web Dev` |

---

## 🔁 Re-running & Deduplication

The pipeline is safe to re-run at any time. `sheets_uploader.py` checks all existing titles in column A before inserting — duplicate articles are automatically skipped.

To scrape fresh articles, simply re-run from `scraper.py`. Existing intermediate `.json` files will be overwritten.

---

## 🧩 Key Design Decisions

**Why Ollama instead of a paid API?**
Ollama runs `llama3.2` fully locally — zero cost, zero data sent externally, works offline. The tradeoff is speed (~10–30s per article on CPU).

**Why `requests` directly instead of the `ollama` Python library?**
The `ollama` library had no configurable timeout, causing silent connection drops during slow CPU inference. Direct HTTP calls via `requests` give explicit control over `timeout`, `num_predict`, and retry logic.

**Why batch `append_rows` instead of row-by-row inserts?**
Google Sheets API has a quota of 300 write requests per minute. A single `append_rows()` call for all 45 rows uses 1 request instead of 45 — far more efficient and quota-friendly.

**Why a two-tier date parser?**
Dev.to returns ISO 8601 dates, but the normalizer is designed to handle any source. `strptime` with 8 explicit formats handles known patterns fast; `dateutil` catches edge cases like `"March 14, 2026"` or fuzzy natural-language dates.

---

## ⚠️ Troubleshooting

| Error | Fix |
|-------|-----|
| `dev.tohttps://` in URLs | Ensure `parse_article_cards()` checks `href.startswith("http")` before prepending base URL |
| `UnicodeDecodeError` on Windows | Always open JSON files with `encoding="utf-8"` |
| `Ollama timed out` | Increase `REQUEST_TIMEOUT` in `summarizer.py` (default: 120s) |
| `SpreadsheetNotFound` | Check `SPREADSHEET_ID` is correct and sheet is shared with the service account email |
| `0 articles normalized` | Re-run `scraper.py` first — `cleaned_articles.json` depends on valid content in `raw_articles.json` |
| Tags show `tag1, tag2, tag3` | The LLM prompt bled into the regex rescue — re-run `summarizer.py` for affected articles |

---

## 📄 License

MIT License — free to use, modify, and distribute.

---

*Pipeline engineered step-by-step with a focus on reliability, zero API costs, and clean data output.*
