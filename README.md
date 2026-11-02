# audio-review-miniapp

Telegram Mini App for human review of store conversations: the current audio pipeline vs Gemma 4 12B.
For each conversation reviewers play the audio, read both results side by side and mark each one
✅ Correct / ❌ Wrong (with an optional note). A 7 PM IST summary in the group shows reviewed / left and
which system scores better.

## How it works
- This repo is the static page only (GitHub Pages). **No conversation data lives here.**
- Data, audio and votes come from the review API on the processing server, reached through a Cloudflare
  quick tunnel. Every request carries Telegram's signed `initData`; the API verifies the signature and that
  the user is a member of the review group.
- The tunnel host is passed in the Mini App start parameter:
  `https://t.me/<bot>/review?startapp=<tunnel-subdomain>` (optionally `__<conversation id>` to open one
  conversation directly). Outside Telegram the page only shows a hint.

## Setup (once)
1. GitHub Pages: Settings → Pages → deploy from `main`, folder `/`.
2. BotFather: `/newapp` → pick the bot → short name `review` → URL
   `https://<github-user>.github.io/audio-review-miniapp/`.

## Review flow
1. The app opens on the next conversation you haven't reviewed (progress bar on top).
2. Play the recording (1× / 1.5×, tap the bar to jump).
3. Step 1: is the **Audio pipeline** text correct? 👍 Correct / 👎 Wrong (pick reasons, no typing needed).
4. Step 2: same for **Gemma 4**. "Compare with …" shows both side by side.
5. "Saved ✓ · Undo" for 5 s, then the next conversation opens. "Skip — can't hear it" moves it to the end.
Team votes stay hidden until you vote. Votes save in the background and retry if the network drops.

## Files
- `index.html` — CSP, loads Telegram's `telegram-web-app.js`, `app.js`, `style.css`.
- `app.js` — one-at-a-time review, prefetch of the next conversation, background saves, list view.
- `style.css` — Apple HIG tokens (system font, 44 pt+ targets, capsule buttons) over Telegram theme colours.
