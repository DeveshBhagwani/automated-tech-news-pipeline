import json
import re
import time
import requests

# ── CONFIG ────────────────────────────────────────────────────────────────────
INPUT_FILE    = "cleaned_articles.json"
OUTPUT_FILE   = "summarized_articles.json"
OLLAMA_MODEL  = "llama3.2"
OLLAMA_URL    = "http://localhost:11434/api/chat"
DELAY         = 2        # seconds between articles
REQUEST_TIMEOUT = 120    # seconds — llama3.2 on CPU can be slow

# ── PROMPT BUILDER ────────────────────────────────────────────────────────────

def build_prompt(title: str, content: str) -> str:
    """
    Minimal prompt — shorter = less tokens = less truncation risk.
    We ask for a simple two-field JSON object only.
    """
    truncated = content[:1200].strip()
    return (
        f'Summarize this article as JSON only. No explanation. No markdown.\n\n'
        f'Title: {title}\n'
        f'Content: {truncated}\n\n'
        f'Return ONLY this JSON (nothing else before or after):\n'
        f'{{"summary": "40 to 60 word summary here", '
        f'"tags": ["tag1", "tag2", "tag3"]}}'
    )

# ── JSON REPAIR ───────────────────────────────────────────────────────────────

def repair_json(raw: str) -> str:
    """
    Attempt to salvage truncated JSON from the LLM by:
    1. Stripping markdown fences
    2. Extracting the largest {...} block
    3. Closing any unclosed brackets/braces
    """
    # Strip fences
    raw = re.sub(r"```(?:json)?", "", raw).strip()

    # Find outermost { ... } — greedy, handles nested braces
    start = raw.find("{")
    if start == -1:
        return raw

    # Walk from end to find last }; if missing, append one
    end = raw.rfind("}")
    if end == -1 or end < start:
        # Close any open arrays and the object
        fragment = raw[start:]
        # Count unclosed [ brackets
        open_arrays = fragment.count("[") - fragment.count("]")
        open_objects = fragment.count("{") - fragment.count("}")
        fragment += "]" * max(open_arrays, 0)
        fragment += "}" * max(open_objects, 0)
        return fragment

    return raw[start:end + 1]

# ── OLLAMA HTTP CALL ──────────────────────────────────────────────────────────

def call_ollama(prompt: str) -> dict | None:
    """
    POST to Ollama's REST API directly using requests.
    More reliable than the ollama Python library for slow CPU inference.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 350,
            "num_ctx": 2048,
        }
    }

    try:
        resp = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        raw_text = resp.json()["message"]["content"].strip()

    except requests.Timeout:
        print(f"    [ERROR] Ollama timed out after {REQUEST_TIMEOUT}s.")
        return None
    except requests.RequestException as e:
        print(f"    [ERROR] HTTP request failed: {e}")
        return None
    except (KeyError, ValueError) as e:
        print(f"    [ERROR] Unexpected Ollama response format: {e}")
        return None

    # ── Attempt JSON parse with repair fallback ───────────────────────────────
    for attempt_text in [raw_text, repair_json(raw_text)]:
        try:
            parsed = json.loads(attempt_text)

            summary = str(parsed.get("summary", "")).strip()
            tags    = parsed.get("tags", [])

            if not summary:
                continue  # try repaired version

            # Normalize tags to exactly 3 strings
            if not isinstance(tags, list):
                tags = ["Tech", "Development", "General"]
            tags = [str(t).strip() for t in tags[:3]]
            while len(tags) < 3:
                tags.append("General")

            return {"summary": summary, "tags": tags}

        except json.JSONDecodeError:
            continue

    # ── Last resort: extract summary from raw text with regex ─────────────────
    summary_match = re.search(r'"summary"\s*:\s*"([^"]{20,})"', raw_text)
    tags_matches  = re.findall(r'"([A-Za-z][A-Za-z0-9 .#+\-]{1,20})"', raw_text)

    if summary_match:
        summary = summary_match.group(1).strip()
        # Filter out the word "summary" and "tags" from tag candidates
        candidate_tags = [
            t for t in tags_matches
            if t.lower() not in ("summary", "tags", "tag1", "tag2", "tag3")
        ][-3:] or ["Tech", "Development", "General"]
        while len(candidate_tags) < 3:
            candidate_tags.append("General")
        print(f"    [WARN] Used regex rescue — partial parse succeeded.")
        return {"summary": summary, "tags": candidate_tags[:3]}

    print(f"    [ERROR] All parse strategies failed.")
    print(f"    [DEBUG] Raw output snippet: {raw_text[:250]}")
    return None

# ── FALLBACK ──────────────────────────────────────────────────────────────────

def generate_fallback(title: str) -> dict:
    return {
        "summary": f"Article: '{title[:80]}'. Full summary unavailable.",
        "tags":    ["Tech", "Development", "General"]
    }

# ── HEALTH CHECK ──────────────────────────────────────────────────────────────

def check_ollama_running() -> bool:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        if r.status_code != 200:
            return False
        models = [m["name"] for m in r.json().get("models", [])]
        model_base = OLLAMA_MODEL.split(":")[0]
        if not any(model_base in m for m in models):
            print(f"[ERROR] Model '{OLLAMA_MODEL}' not found.")
            print(f"        Available: {models}")
            print(f"        Run: ollama pull {OLLAMA_MODEL}")
            return False
        print(f"[INFO] Found models: {models}")
        return True
    except Exception as e:
        print(f"[ERROR] Cannot reach Ollama: {e}")
        print(f"        Make sure Ollama is running (check system tray).")
        return False

# ── MAIN PIPELINE ─────────────────────────────────────────────────────────────

def summarize_articles(input_file=INPUT_FILE, output_file=OUTPUT_FILE) -> list[dict]:

    print(f"[INFO] Loading cleaned articles from '{input_file}'...")
    with open(input_file, "r", encoding="utf-8") as f:
        articles: list[dict] = json.load(f)
    print(f"[INFO] {len(articles)} articles loaded.\n")

    if not articles:
        print("[ERROR] No articles found. Run normalizer.py first.")
        return []

    summarized = []
    failed     = 0

    for idx, article in enumerate(articles, start=1):
        title   = article.get("title", "Untitled")
        content = article.get("content", "")

        print(f"  [{idx}/{len(articles)}] Summarizing: {title[:65]}...")

        if len(content) < 80:
            print("    [SKIP] Content too short — using fallback.")
            result = generate_fallback(title)
        else:
            prompt = build_prompt(title, content)
            result = None

            for attempt in range(1, 3):
                result = call_ollama(prompt)
                if result:
                    break
                print(f"    [RETRY] Attempt {attempt}/2 failed. Waiting 3s...")
                time.sleep(3)

            if not result:
                print("    [WARN] All retries exhausted — using fallback.")
                result = generate_fallback(title)
                failed += 1

        enriched = {
            "title":   title,
            "author":  article.get("author",  "Unknown"),
            "date":    article.get("date",    "1900-01-01"),
            "url":     article.get("url",     ""),
            "summary": result["summary"],
            "tags":    ", ".join(result["tags"]),
        }
        summarized.append(enriched)

        print(f"    ✓ Summary : {result['summary'][:90]}...")
        print(f"    ✓ Tags    : {result['tags']}")

        time.sleep(DELAY)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summarized, f, indent=2, ensure_ascii=False)

    print(f"\n[DONE] {len(summarized)} articles summarized "
          f"({failed} used fallback). Saved to '{output_file}'.")
    return summarized

# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[INFO] Checking Ollama service...")
    if not check_ollama_running():
        print("[ABORT] Fix Ollama connection before proceeding.")
        exit(1)
    print(f"[INFO] Ollama ready. Model: '{OLLAMA_MODEL}'\n")

    results = summarize_articles()

    print("\n── SAMPLE SUMMARIZED RECORD ───────────────────────────────────")
    if results:
        s = results[0]
        print(f"  Title   : {s['title']}")
        print(f"  Author  : {s['author']}")
        print(f"  Date    : {s['date']}")
        print(f"  Summary : {s['summary']}")
        print(f"  Tags    : {s['tags']}")