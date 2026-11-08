#!/bin/zsh
# Runs Bitcoin Daily on this Mac:
#   - com.btcdaily.dashboard: builds the dashboard + sends the iPhone notification daily at 07:00
#   - com.btcdaily.server:    serves the dashboard on your Wi-Fi so the notification link opens on your iPhone
# Remove both with:  ./install_schedule.sh --remove
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
PORT=8765
UID_GUI="gui/$(id -u)"
LABELS=(com.btcdaily.dashboard com.btcdaily.server)

for label in $LABELS; do
  launchctl bootout "$UID_GUI/$label" 2>/dev/null || true
done
if [[ "$1" == "--remove" ]]; then
  for label in $LABELS; do rm -f "$AGENTS/$label.plist"; done
  echo "Removed the daily run and the dashboard server."
  exit 0
fi

mkdir -p "$DIR/output" "$AGENTS" "$HOME/Library/Logs/BitcoinDaily"
PY="$(command -v python3)"
for label in $LABELS; do
  sed -e "s#__PYTHON__#$PY#" -e "s#__DIR__#$DIR#g" -e "s#__PORT__#$PORT#g" -e "s#__HOME__#$HOME#g" \
    "$DIR/$label.plist.template" > "$AGENTS/$label.plist"
  launchctl bootstrap "$UID_GUI" "$AGENTS/$label.plist"
done

# Point the notification link at this Mac (unless you've set your own DASHBOARD_URL)
URL="http://$(scutil --get LocalHostName).local:$PORT/"
[[ -f "$DIR/.env" ]] || cp "$DIR/.env.example" "$DIR/.env"
if grep -q '^DASHBOARD_URL=$' "$DIR/.env"; then
  sed -i '' "s#^DASHBOARD_URL=\$#DASHBOARD_URL=$URL#" "$DIR/.env"
fi

echo "Installed."
echo "  Daily run: 07:00 (if the Mac is asleep then, it runs as soon as it wakes). Log: ~/Library/Logs/BitcoinDaily/run.log"
echo "  Dashboard on your Wi-Fi: $(grep '^DASHBOARD_URL=' "$DIR/.env" | cut -d= -f2-)"
echo "Run it right now with:  launchctl kickstart $UID_GUI/com.btcdaily.dashboard"
