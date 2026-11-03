#!/usr/bin/env bash
# Installs and enables the three review-app user services; starting them is a separate, explicit step.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
units=(review-tunnel.service review-api.service review-poster.service)
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
for u in "${units[@]}"; do
  install -m 644 "$here/systemd/$u" "$HOME/.config/systemd/user/$u"
done
systemctl --user daemon-reload
systemctl --user enable "${units[@]}"
echo "installed and enabled: ${units[*]}"
echo "start: systemctl --user start ${units[*]}"
