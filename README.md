# audio-review-miniapp

Telegram Mini App for human review of store conversations (calls and in-store CCTV audio). Reviewers play the
recording, read each system's transcript, mark lines ✓/✗, and submit Correct/Wrong for the whole result.

- **Client group** ("Audio Pipeline calls"): every member sees only the audio pipeline.
- **Cost group** ("Gemini Cost for Audio Pipeline"): opened from its pinned card, members see every model side by
  side plus the Benchmark; the owner also gets the Team page.

## Layout
```
web/       static Mini App served by GitHub Pages (ES modules, no build step, no dependencies)
  index.html, css/style.css, js/*.js     entry: js/main.js
server/    review API + Telegram poster (Python 3.10+, stdlib only)
  review_app/   config, telegram (auth, modes), store (SQLite), results, views, roles, reports,
                launcher, workers, scheduler, http, poster, __main__
  tests/        pytest
deploy/    systemd user units, env example, install script for thor02
.github/workflows/pages.yml   publishes web/ only, stamps the commit into ?v= for cache busting
```

## How it fits together
1. The audio pipeline writes results to `live_results/<store>/<YYYY-MM-DD>/<stem>.json` (plus
   `<stem>.<model>.json` for each model) on thor02.
2. `review_app.poster` posts each new conversation to the client group with a 📝 Review button.
3. `review_app serve` answers the Mini App on `127.0.0.1:8787`, reached through a Cloudflare quick tunnel. Every
   request carries Telegram's signed `initData`; the server checks the signature and group membership.
4. The launch link picks the view: `startapp=<tunnel>` (client) or `startapp=<tunnel>____cost` (cost group;
   also requires membership of the cost group). The tunnel host changes on restart; the scheduler re-points the
   pinned launchers when it does.
5. At 19:00 IST the server posts the day's summary (pipeline only to the client group, full benchmark to the cost
   group) and alerts the cost group when a model worker stops.

## Develop
```
cd server
python3 -m pytest -q
ruff check . && ruff format --check .
```
Frontend: `node --input-type=module --check < web/js/<file>.js`; for a browser check, serve a copy of `web/`
with `__V__` replaced and stub `window.Telegram.WebApp` and `fetch`.

## Deploy
- **Frontend:** push to `main`; the Pages workflow publishes `web/` (Settings → Pages → Source: GitHub Actions).
  BotFather's Mini App URL stays `https://haripratap-1p.github.io/audio-review-miniapp/`.
- **Server (thor02):** code runs from a clone at `~/Documents/hp_workspace/audio-review-miniapp`; state and data
  stay in `REVIEW_HOME` (`~/SanjAI/audio-inference`: `reviews.db`, `roles.json`, launcher pins, logs, worker pid
  files, `live_results/`).
  1. Create `~/.config/review-app/review.env` from `deploy/review.env.example` (chmod 600; leave unused keys out).
  2. `deploy/install.sh` installs and enables `review-tunnel`, `review-api`, `review-poster` (user units; linger on).
  3. `systemctl --user start review-tunnel review-api review-poster`.
  - Update: `git -C ~/Documents/hp_workspace/audio-review-miniapp fetch && git checkout <commit>`, run the tests,
    then `systemctl --user restart review-api review-poster`.
  - Logs: `~/SanjAI/audio-inference/{review_api,telegram_poster,review_tunnel}.log`.
