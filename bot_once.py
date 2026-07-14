"""
Reddit RSS -> Discord webhook bot (single-run version for GitHub Actions).

Unlike bot.py (which loops forever), this runs ONCE per invocation: check
the feed, post anything new, save state, and exit. GitHub Actions calls
this on a schedule (see .github/workflows/reddit-bot.yml), and a workflow
step commits the updated seen_posts.json back to the repo so state
persists between runs.
"""

import html
import json
import os
import re
import sys
import time
from pathlib import Path

import feedparser
import requests

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
SEEN_PATH = BASE_DIR / "seen_posts.json"
MAX_SEEN_IDS = 5000

# On GitHub Actions, the webhook URL comes from a repository secret injected
# as an environment variable (see the workflow file) -- not from a .env file.
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
if not DISCORD_WEBHOOK_URL:
    sys.exit("Missing DISCORD_WEBHOOK_URL environment variable / secret.")

HEADERS = {"User-Agent": "reddit-discord-rss-bot/1.0 (personal use)"}
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("subreddits", [])
    cfg.setdefault("keywords", [])
    cfg.setdefault("sort", "new")
    cfg.setdefault("limit", 25)
    return cfg


def load_seen() -> set:
    if SEEN_PATH.exists():
        with open(SEEN_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set) -> None:
    trimmed = list(seen)[-MAX_SEEN_IDS:]
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(trimmed, f)


def matches_keywords(title: str, summary: str, keywords: list) -> bool:
    if not keywords:
        return True
    haystack = f"{title} {summary}".lower()
    return any(kw.lower() in haystack for kw in keywords)


def fetch_combined_feed(subreddits, sort, limit, retries=3):
    combined = "+".join(subreddits)
    url = f"https://www.reddit.com/r/{combined}/{sort}/.rss?limit={limit}"
    resp = None
    for attempt in range(retries):
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 429:
            wait = 20 * (attempt + 1)
            print(f"Rate limited, waiting {wait}s before retry")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return feedparser.parse(resp.content)
    resp.raise_for_status()


def subreddit_from_link(link: str) -> str:
    parts = link.split("/r/", 1)
    if len(parts) == 2:
        return parts[1].split("/", 1)[0]
    return "unknown"


def extract_summary_parts(summary_html: str):
    direct_link = None
    link_match = re.search(r'<a href="([^"]+)">\s*\[link\]', summary_html)
    if link_match:
        direct_link = html.unescape(link_match.group(1))

    thumb = None
    img_match = re.search(r'<img src="([^"]+)"', summary_html)
    if img_match:
        thumb = html.unescape(img_match.group(1))

    text = re.sub(r"<[^>]+>", " ", summary_html)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"submitted by.*$", "", text, flags=re.IGNORECASE).strip()

    image_url = None
    if direct_link and direct_link.lower().split("?")[0].endswith(IMAGE_EXTENSIONS):
        image_url = direct_link
    elif thumb and thumb.startswith("http") and "thumbs.redditmedia.com" not in thumb:
        image_url = thumb

    return image_url, text


def send_to_discord(title, link, subreddit, author, image_url=None, description=""):
    embed = {
        "title": title[:256],
        "url": link,
        "color": 0xFF4500,
        "footer": {"text": f"r/{subreddit} • posted by {author}"},
    }
    if description:
        embed["description"] = description[:300]
    if image_url:
        embed["image"] = {"url": image_url}

    resp = requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=15)
    if resp.status_code >= 300:
        print(f"Discord webhook error {resp.status_code}: {resp.text}")


def main():
    config = load_config()
    if not config["subreddits"]:
        sys.exit("config.json has no subreddits listed.")

    seen = load_seen()
    is_first_run = len(seen) == 0

    feed = fetch_combined_feed(config["subreddits"], config["sort"], config["limit"])

    if is_first_run:
        # Seed "seen" from the current feed without posting, so we don't
        # dump a backlog of old posts the very first time this runs.
        for entry in feed.entries:
            seen.add(entry.get("id") or entry.get("link"))
        save_seen(seen)
        print(f"First run: seeded {len(seen)} existing posts as 'seen' without posting.")
        return

    posted = 0
    for entry in reversed(feed.entries):
        post_id = entry.get("id") or entry.get("link")
        if post_id in seen:
            continue
        seen.add(post_id)

        title = entry.get("title", "(no title)")
        summary = entry.get("summary", "")
        if not matches_keywords(title, summary, config["keywords"]):
            continue

        link = entry.get("link", "")
        author = entry.get("author", "unknown").replace("/u/", "")
        subreddit = subreddit_from_link(link)
        image_url, description = extract_summary_parts(summary)

        send_to_discord(title, link, subreddit, author, image_url, description)
        print(f"Posted: {title} (r/{subreddit})")
        posted += 1

    save_seen(seen)
    print(f"Done. Posted {posted} new item(s).")


if __name__ == "__main__":
    main()
