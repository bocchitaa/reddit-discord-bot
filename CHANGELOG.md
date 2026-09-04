# Changelog

A running log of changes to this bot, in plain English, newest first.

## 2026-07-14 — Image-only posts, cleaner embeds

- **Skip text-only posts.** Posts with no image/media attached are no
  longer forwarded to Discord at all — only posts with an actual picture
  get sent.
- **Removed the caption/description text** from the embed. Previously it
  showed a preview of the post's body text below the title; now the embed
  is just the title, the image, and a link back to the post.
- **Strip hashtags from titles.** Any `#word` patterns in a post's title
  (like `#Genshin`) are now removed before posting.

## 2026-07-14 — Initial GitHub Actions version

- Rebuilt the bot to run on a schedule via GitHub Actions (every 15
  minutes) instead of needing a PC left running.
- Switched from the Reddit API (which now requires manual approval) to
  Reddit's public RSS feeds — no login or API key needed.
- Switched from a Discord bot account to a Discord webhook, since the bot
  only ever needs to send messages, not receive them.
- Added image/thumbnail extraction from each post's RSS data, so posts
  show a real preview image instead of just a bare link.
- Added rate-limit handling (retry with backoff) since Reddit strictly
  limits RSS requests to roughly 1 per minute.
