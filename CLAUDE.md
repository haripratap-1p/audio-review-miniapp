# CLAUDE.md

Review Mini App: `web/` (GitHub Pages), `server/` (thor02 API + poster), `deploy/` (systemd). See README.md.

## Rules
- Ask before every code change, commit or push; show the diff first; one commit per change.
- Commits: `git -c user.name="Hari Pratap" -c user.email=haripratap@urmedz.in commit`. No AI attribution anywhere.
- Code comments: at most one short line. No docstrings or comment blocks; longer notes go in README.md.
- Server: stdlib only, type hints, settings only via `review_app.config.get_settings()`, all state under
  `REVIEW_HOME`. Run `pytest` and `ruff check`/`ruff format --check` in `server/` before committing.
- Web: ES modules, no build step or dependencies; every relative import ends in `?v=__V__`; keep the CSP.
- Never commit secrets, `*.env`, `*.db`, logs or `live_results/`. Tokens live only in thor02
  `~/.config/review-app/review.env` (chmod 600) and are never printed.
- Access rules: client view = pipeline only for everyone; full view only via the cost launcher **and** cost-group
  membership. Don't loosen `mode()`, `view()` or `is_member()` without asking.
- Deploying to thor02 restarts user services there; don't touch other services, tunnels or `~/SanjAI` files.
