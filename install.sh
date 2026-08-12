#!/usr/bin/env bash
# install.sh — install the ghostty theme sync scripts to ~/.local/bin.
#
# Usage:
#   ./install.sh                install scripts
#   ./install.sh --with-auto-sync   also install the launchd WatchPaths agent
#                                   (auto-sync on ghostty/herdr changes; macOS)
#
# After installing, add a keybinding to ~/.config/herdr/config.toml:
#   [[keys.command]]
#   key = "prefix+alt+s"
#   type = "shell"
#   command = "herdr-theme-sync"
#   description = "sync herdr theme from ghostty"
# and copy the sidebar/theme rows from config.example.toml.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
WITH_AUTO_SYNC=0
for arg in "$@"; do
  [ "$arg" = "--with-auto-sync" ] && WITH_AUTO_SYNC=1
done

mkdir -p "$BIN"
install -m 0755 "$REPO/theme-sync.py" "$BIN/herdr-theme-sync"
install -m 0755 "$REPO/refresh.sh" "$BIN/herdr-refresh-sidebar"
install -m 0755 "$REPO/herdr-auto-sync" "$BIN/herdr-auto-sync"
echo "installed: $BIN/herdr-theme-sync, herdr-refresh-sidebar, herdr-auto-sync"

if [ "$WITH_AUTO_SYNC" = "1" ]; then
  PLIST="$HOME/Library/LaunchAgents/com.themuuln.herdr-auto-sync.plist"
  mkdir -p "$(dirname "$PLIST")"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>com.themuuln.herdr-auto-sync</string>
	<key>ProgramArguments</key>
	<array>
		<string>/bin/bash</string>
		<string>$BIN/herdr-auto-sync</string>
	</array>
	<key>WatchPaths</key>
	<array>
		<string>$HOME/.config/ghostty/config</string>
		<string>$HOME/.config/ghostty/themes</string>
		<string>$HOME/.config/herdr/herdr.sock</string>
		<string>$HOME/.config/herdr/herdr-client.sock</string>
	</array>
	<key>ThrottleInterval</key>
	<integer>10</integer>
	<key>EnvironmentVariables</key>
	<dict>
		<key>PATH</key>
		<string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$BIN</string>
		<key>HOME</key>
		<string>$HOME</string>
	</dict>
	<key>StandardOutPath</key>
	<string>/tmp/herdr-auto-sync.log</string>
	<key>StandardErrorPath</key>
	<string>/tmp/herdr-auto-sync.err.log</string>
</dict>
</plist>
EOF
  if launchctl list | grep -q com.themuuln.herdr-auto-sync; then
    launchctl unload "$PLIST"
  fi
  launchctl load "$PLIST"
  echo "launchd agent installed and loaded: $PLIST"
  echo "  watches: ghostty config/themes + herdr sockets → auto theme-sync + token refresh"
fi

echo
echo "Next steps:"
echo "  1. copy the theme/sidebar rows from config.example.toml into ~/.config/herdr/config.toml"
echo "  2. add the prefix+alt+s keybinding (see the header of this script)"
echo "  3. run herdr-theme-sync once to derive colors from your Ghostty theme"
