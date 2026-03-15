import requests
from bs4 import BeautifulSoup
import time
import json

# ── CONFIG ────────────────────────────────────────────────────────────────────
BASE_URL = "https://dev.to/t/webdev"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
MAX_PAGES = 3          # scrape pages 1-3
DELAY_SECONDS = 2      # polite crawl delay between requests

# ── HELPERS ───────────────────────────────────────────────────────────────────

def fetch_page(url: str) -> BeautifulSoup | None:
    """
    Fetch a single URL and return a BeautifulSoup object.
    Returns None if the request fails.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return BeautifulSoup(response.text, "lxml")
    except requests.RequestException as e:
        print(f"[ERROR] Failed to fetch {url}: {e}")
        return None


def parse_article_cards(soup: BeautifulSoup) -> list[dict]:
    articles = []
    cards = soup.find_all("div", class_="crayons-story")

    if not cards:
        print("[WARN] No article cards found on this page — check the HTML selector.")
        return articles

    for card in cards:
        # ── Title & article URL ──────────────────────────────────────────────
        title_tag = card.find("h2", class_="crayons-story__title")
        if not title_tag:
            continue
        anchor = title_tag.find("a")
        title = anchor.get_text(strip=True) if anchor else "N/A"

        #handle both absolute and relative hrefs
        if anchor:
            href = anchor["href"]
            article_url = href if href.startswith("http") else "https://dev.to" + href
        else:
            article_url = None

        # ── Author ───────────────────────────────────────────────────────────
        author_tag = card.find("a", class_="crayons-story__secondary")
        author = author_tag.get_text(strip=True) if author_tag else "Unknown"

        # ── Date ─────────────────────────────────────────────────────────────
        time_tag = card.find("time")
        raw_date = time_tag["datetime"] if time_tag and time_tag.has_attr("datetime") else "Unknown"

        articles.append({
            "title":    title,
            "author":   author,
            "raw_date": raw_date,
            "url":      article_url,
            "content":  None,
        })

    return articles


def scrape_article_content(url: str) -> str:
    """
    Visit an individual article page and extract the main body text.
    Returns a raw HTML string — cleaning happens in Phase 2.
    """
    if not url:
        return ""

    soup = fetch_page(url)
    if not soup:
        return ""

    # Dev.to wraps article body in <div id="article-body">
    body = soup.find("div", id="article-body")
    if body:
        return str(body)           # raw HTML; BeautifulSoup cleans in Phase 2

    # Fallback: grab the largest <article> block
    article = soup.find("article")
    return str(article) if article else ""


# ── MAIN PIPELINE ─────────────────────────────────────────────────────────────

def run_scraper(base_url: str = BASE_URL, max_pages: int = MAX_PAGES) -> list[dict]:
    """
    Orchestrate pagination: loop through pages 1..max_pages,
    collect article metadata, then fetch full content for each article.
    Returns the complete list of raw article dicts.
    """
    all_articles = []

    for page_num in range(1, max_pages + 1):
        page_url = f"{base_url}?page={page_num}"
        print(f"\n[INFO] Scraping page {page_num}: {page_url}")

        soup = fetch_page(page_url)
        if not soup:
            print(f"[WARN] Skipping page {page_num} due to fetch error.")
            continue

        cards = parse_article_cards(soup)
        print(f"[INFO] Found {len(cards)} articles on page {page_num}.")

        # Fetch full content for each article on this page
        for idx, article in enumerate(cards, start=1):
            print(f"  [{idx}/{len(cards)}] Fetching content: {article['title'][:60]}...")
            article["content"] = scrape_article_content(article["url"])
            time.sleep(DELAY_SECONDS)   # rate limiting — be a polite crawler

        all_articles.extend(cards)

        # Respect the server between page fetches
        if page_num < max_pages:
            time.sleep(DELAY_SECONDS)

    print(f"\n[DONE] Total articles scraped: {len(all_articles)}")
    return all_articles


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = run_scraper()

    # Persist raw output so Phase 2 can read it without re-scraping
    output_file = "raw_articles.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"[INFO] Raw data saved to '{output_file}'")

    # Quick sanity preview
    print("\n── SAMPLE RECORD ──────────────────────────────────────────────")
    if results:
        sample = results[0]
        print(f"  Title   : {sample['title']}")
        print(f"  Author  : {sample['author']}")
        print(f"  Date    : {sample['raw_date']}")
        print(f"  URL     : {sample['url']}")
        print(f"  Content : {str(sample['content'])[:120]}...")
