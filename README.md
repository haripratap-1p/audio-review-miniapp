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

## Files
- `index.html` — loads Telegram's `telegram-web-app.js`, `app.js`, `style.css`.
- `app.js` — list (To review / My reviews / All, date filter), conversation view, votes.
- `style.css` — follows the Telegram theme colours; two columns from 600 px wide.
