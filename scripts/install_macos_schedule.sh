#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.ai-shopping-radar.update.plist"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.ai-shopping-radar.update</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$ROOT_DIR/scripts/update_content.py</string>
    <string>--days</string>
    <string>30</string>
    <string>--limit</string>
    <string>8</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>11</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/update.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/update.err.log</string>
</dict>
</plist>
PLIST
launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST"
echo "Installed daily updater at 11:00 Asia/Shanghai: $PLIST"
