#!/usr/bin/env bash
# Installs the review-app user units and enables the services and the judge timer; starting is a separate step.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
units=(review-tunnel.service review-api.service review-poster.service)
enabled=("${units[@]}" review-judge.timer)  # review-judge.service runs only from its timer
env_file="$HOME/.config/review-app/review.env"

if [[ ! -f "$env_file" ]]; then
  echo "missing $env_file (see deploy/review.env.example)" >&2
  exit 1
fi
if [[ "$(stat -c %a "$env_file")" != "600" ]]; then
  echo "$env_file must be chmod 600" >&2
  exit 1
fi

mkdir -p "$HOME/.config/systemd/user"
for u in "${units[@]}" review-judge.service review-judge.timer; do
  install -m 644 "$here/systemd/$u" "$HOME/.config/systemd/user/$u"
done
systemctl --user daemon-reload
systemctl --user enable "${enabled[@]}"
echo "installed and enabled: ${enabled[*]}"
echo "start: systemctl --user start ${enabled[*]}"
