#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON3=$(which python3 2>/dev/null || true)
APP_NAME="Ship Streak"
APP_PATH="/Applications/$APP_NAME.app"
PLIST_LABEL="com.shipstreak.app"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
CONFIG_DIR="$HOME/.config/ship-streak"
LOG_DIR="$CONFIG_DIR/logs"

echo "=== Ship Streak Setup ==="
echo ""

# 1. Check Python 3
if [ -z "$PYTHON3" ]; then
    echo "ERROR: Python 3 not found. Install from https://python.org or: brew install python3"
    exit 1
fi
PYTHON3="$(readlink -f "$PYTHON3" 2>/dev/null || python3 -c "import sys; print(sys.executable)")"
echo "[1/6] Python 3 found: $($PYTHON3 --version) at $PYTHON3"

# 2. Check gh CLI (optional)
if command -v gh &>/dev/null && gh auth status &>/dev/null; then
    echo "[2/6] GitHub CLI found and authenticated (will auto-detect credentials)."
    HAS_GH=1
else
    echo "[2/6] GitHub CLI not found or not authenticated (optional, setup window will handle auth)."
    HAS_GH=0
fi

# 3. Install dependencies
echo "[3/6] Installing Python dependencies..."
$PYTHON3 -m pip install -q requests pyobjc-framework-Cocoa 2>&1 | grep -v "already satisfied" || true

# 4. Detect username and create config
echo "[4/6] Setting up configuration..."
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

# 5. Create macOS app bundle
echo "[5/6] Installing $APP_NAME.app..."

# Kill running instance if any
pkill -f "ship_streak.py" 2>/dev/null || true
sleep 1

rm -rf "$APP_PATH"
mkdir -p "$APP_PATH/Contents/MacOS" "$APP_PATH/Contents/Resources"

# Copy icon
if [ -f "$SCRIPT_DIR/resources/AppIcon.icns" ]; then
    cp "$SCRIPT_DIR/resources/AppIcon.icns" "$APP_PATH/Contents/Resources/AppIcon.icns"
fi

# Info.plist
cat > "$APP_PATH/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleName</key>
	<string>$APP_NAME</string>
	<key>CFBundleDisplayName</key>
	<string>$APP_NAME</string>
	<key>CFBundleIdentifier</key>
	<string>$PLIST_LABEL</string>
	<key>CFBundleVersion</key>
	<string>1.0</string>
	<key>CFBundleShortVersionString</key>
	<string>1.0</string>
	<key>CFBundleExecutable</key>
	<string>ShipStreak</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleIconFile</key>
	<string>AppIcon</string>
	<key>LSUIElement</key>
	<true/>
	<key>LSMinimumSystemVersion</key>
	<string>12.0</string>
</dict>
</plist>
PLIST

# Launcher script
cat > "$APP_PATH/Contents/MacOS/ShipStreak" <<LAUNCHER
#!/bin/bash
cd "$SCRIPT_DIR"
exec "$PYTHON3" ship_streak.py
LAUNCHER
chmod +x "$APP_PATH/Contents/MacOS/ShipStreak"

# Touch to refresh Finder/Spotlight/LaunchServices cache
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_PATH" 2>/dev/null || true

echo "  Installed: $APP_PATH"

# 6. Install LaunchAgent (auto-start on login)
echo "[6/6] Installing LaunchAgent for auto-start on login..."
launchctl bootout "gui/$(id -u)/$PLIST_LABEL" 2>/dev/null || true

cat > "$PLIST_PATH" <<AGENT
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>$PLIST_LABEL</string>
	<key>ProgramArguments</key>
	<array>
		<string>/usr/bin/open</string>
		<string>-a</string>
		<string>$APP_PATH</string>
	</array>
	<key>RunAtLoad</key>
	<true/>
	<key>KeepAlive</key>
	<false/>
	<key>StandardOutPath</key>
	<string>$LOG_DIR/stdout.log</string>
	<key>StandardErrorPath</key>
	<string>$LOG_DIR/stderr.log</string>
</dict>
</plist>
AGENT

echo ""
echo "=== Setup Complete ==="
echo ""
echo "  Launch now:    open -a \"$APP_NAME\""
echo "  Or find it:    Cmd+Space, type \"Ship Streak\""
echo "  Auto-starts:   on every login"
echo ""
echo "  Controls:"
echo "    - Drag widget to reposition"
echo "    - Right-click widget for menu (theme, send to back, hide, refresh, quit)"
echo "    - Menu bar icon for show/hide and quit"
echo "    - Cmd+Space \"Ship Streak\" to relaunch after quit"
echo ""
echo "  Uninstall:     ./setup.sh --uninstall"
echo ""

# Auto-launch
open -a "$APP_NAME"
