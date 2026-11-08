#!/bin/zsh
# Installs a daily 07:00 run on this Mac (launchd). Remove with:  ./install_schedule.sh --remove
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.btcdaily.dashboard.plist"
if [[ "$1" == "--remove" ]]; then
  launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"; echo "Schedule removed."; exit 0
fi
mkdir -p "$DIR/output" "$HOME/Library/LaunchAgents"
sed -e "s#__PYTHON__#$(command -v python3)#" -e "s#__DIR__#$DIR#g" "$DIR/com.btcdaily.dashboard.plist.template" > "$PLIST"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed: runs daily at 07:00 (if the Mac is asleep, it runs when it wakes). Log: $DIR/output/run.log"
