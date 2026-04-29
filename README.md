# Ship Streak

A macOS desktop widget that displays your GitHub contribution graph, always visible on your screen. Stay accountable for shipping every day.

![macOS](https://img.shields.io/badge/macOS-12+-black)
![Python](https://img.shields.io/badge/Python-3.8+-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## What it does

- Renders the full GitHub contribution heatmap (53 weeks) as a floating desktop widget
- Shows current streak, today's contributions, and longest streak
- Menu bar icon with streak count for quick glance
- Auto-refreshes every 3 minutes and on wake from sleep
- 5 themes: GitHub Classic, Midnight Inferno, Malibu Dream, Ocean Drift, Minesweeper
- Draggable, works on all Spaces

## Requirements

- **macOS 12+** (Monterey or later)
- **Python 3.8+**
- **GitHub CLI (`gh`)** - optional, for auto-detection of credentials ([install](https://cli.github.com))

## Install

```bash
git clone https://github.com/ekatasingh1107/ship-streak.git
cd ship-streak
./setup.sh
```

This installs **Ship Streak.app** in `/Applications` and launches it. The app:

- Shows up in **Spotlight** (Cmd+Space, type "Ship Streak")
- Shows up in **Launchpad** and **Finder**
- **Auto-starts on login** via LaunchAgent
- Has **no Dock icon** (menu bar only)

On first launch, if no credentials are found, a setup window will appear where you can enter your GitHub username and a personal access token (no special scopes needed).

## Relaunch after Quit

Cmd+Space, type "Ship Streak", hit Enter. Like any other app.

## Authentication

Ship Streak tries credentials in this order:
1. **macOS Keychain** - tokens saved from the setup window
2. **GitHub CLI** - `gh auth token` (if `gh` is installed and authenticated)

If neither is available, the setup window opens automatically.

## Configuration

Config lives at `~/.config/ship-streak/config.json` (never in the repo):

```json
{
  "username": "your-github-username"
}
```

Tokens are stored in macOS Keychain (service: `ship-streak-github`), never in config files.

## Controls

### Widget (right-click)
- **Refresh Now** - fetch latest data
- **Open GitHub Profile** - opens in browser
- **Send to Back / Bring to Front** - toggle floating behavior
- **Hide Widget** - hides the widget (reopen from menu bar)
- **Theme** - switch between 5 themes
- **Quit Ship Streak** - fully exit

### Menu Bar
- **Show/Hide Widget** - toggle widget visibility
- **Send to Back / Bring to Front** - toggle floating
- **Refresh** - fetch latest data
- **Theme** - switch themes
- **Quit Ship Streak** - fully exit

### Drag
Click and drag anywhere on the widget to reposition it.

## Uninstall

```bash
# Stop and remove auto-start
launchctl bootout gui/$(id -u)/com.shipstreak.app

# Remove app, LaunchAgent, config
rm -rf "/Applications/Ship Streak.app"
rm ~/Library/LaunchAgents/com.shipstreak.app.plist
rm -rf ~/.config/ship-streak
```

## How it works

1. Reads your GitHub token from macOS Keychain or `gh` CLI
2. Queries GitHub's GraphQL API for your contribution calendar (last year)
3. Renders the heatmap as a native macOS window using PyObjC
4. Auto-refreshes every 3 minutes via NSTimer
5. Listens for `NSWorkspaceDidWakeNotification` to refresh on laptop open

API usage: ~20 requests/hour (GitHub allows 5,000/hour for authenticated users).

## Security

- **Token in macOS Keychain only** - never in config files or the repo
- **No personal data in repo** - username stored in local config only
- **Read-only API access** - only reads public contribution data
- **No network calls** except to `api.github.com`
- **Secure input** - token field is masked during setup

## License

MIT
