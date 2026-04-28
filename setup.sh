#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON3=$(which python3 2>/dev/null || true)
PLIST_NAME="com.ship-streak.plist"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME"
CONFIG_DIR="$HOME/.config/ship-streak"
LOG_DIR="$CONFIG_DIR/logs"

echo "=== Ship Streak Setup ==="
echo ""

# 1. Check Python 3
if [ -z "$PYTHON3" ]; then
    echo "ERROR: Python 3 not found. Install from https://python.org or: brew install python3"
    exit 1
fi
PY_VERSION=$($PYTHON3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
echo "[1/5] Python 3 found: $($PYTHON3 --version)"

# 2. Check gh CLI (optional)
if command -v gh &>/dev/null && gh auth status &>/dev/null; then
    echo "[2/5] GitHub CLI found and authenticated (will auto-detect credentials)."
    HAS_GH=1
else
    echo "[2/5] GitHub CLI not found or not authenticated (optional, setup window will handle auth)."
    HAS_GH=0
fi

# 3. Install dependencies
echo "[3/5] Installing Python dependencies..."
$PYTHON3 -m pip install -q requests pyobjc-framework-Cocoa 2>&1 | grep -v "already satisfied" || true

# 4. Detect username and create config
echo "[4/5] Setting up configuration..."
mkdir -p "$CONFIG_DIR" "$LOG_DIR"
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    USERNAME=""
    if [ "$HAS_GH" -eq 1 ]; then
        USERNAME=$(gh api user --jq .login 2>/dev/null || echo "")
    fi
    if [ -n "$USERNAME" ]; then
        echo "{\"username\": \"$USERNAME\"}" > "$CONFIG_DIR/config.json"
        echo "  Config created for: $USERNAME"
    else
        echo "  No config created. The setup window will handle this on first launch."
    fi
else
    USERNAME=$(python3 -c "import json; print(json.load(open('$CONFIG_DIR/config.json')).get('username',''))" 2>/dev/null)
    echo "  Config exists for: $USERNAME"
fi

# 5. Install LaunchAgent (auto-start on login)
echo "[5/5] Installing LaunchAgent..."
launchctl bootout "gui/$(id -u)/$PLIST_NAME" 2>/dev/null || true

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON3</string>
        <string>$SCRIPT_DIR/ship_streak.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
EOF

echo ""
echo "=== Setup Complete ==="
echo ""
echo "  Start now:     python3 $SCRIPT_DIR/ship_streak.py"
echo "  Auto-start:    launchctl bootstrap gui/$(id -u) $PLIST_PATH"
echo "  Stop:          launchctl bootout gui/$(id -u)/$PLIST_NAME"
echo "  Config:        $CONFIG_DIR/config.json"
echo "  Logs:          $LOG_DIR/"
echo ""
echo "  Controls:"
echo "    - Drag widget to reposition"
echo "    - Right-click widget for menu (send to back, hide, refresh, quit)"
echo "    - Menu bar icon for show/hide and quit"
echo ""
