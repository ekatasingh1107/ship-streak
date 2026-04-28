#!/usr/bin/env python3
"""Ship Streak - GitHub Contribution Streak Tracker for macOS Desktop"""

import json
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

import requests
import objc
from AppKit import (
    NSApplication, NSWindow, NSView, NSColor, NSFont,
    NSBackingStoreBuffered, NSBezierPath,
    NSForegroundColorAttributeName, NSFontAttributeName,
    NSAttributedString, NSScreen, NSWorkspace, NSMenu, NSMenuItem,
    NSStatusBar, NSVariableStatusItemLength,
    NSTextField, NSSecureTextField, NSButton,
    NSBezelStyleRounded,
)
from Foundation import NSObject, NSTimer, NSPoint, NSSize, NSRect

# prevent GC of controllers
_refs = []

# --- Paths ---
CONFIG_DIR = Path.home() / ".config" / "ship-streak"
CONFIG_FILE = CONFIG_DIR / "config.json"
GRAPHQL_URL = "https://api.github.com/graphql"
REFRESH_INTERVAL = 180
FLOATING_LEVEL = 3   # NSFloatingWindowLevel - above all windows
DESKTOP_LEVEL = -1   # above desktop icons, below all app windows

# --- GitHub dark theme colors ---
BG = (0.0863, 0.1059, 0.1333, 0.95)
BORDER = (0.1882, 0.2118, 0.2392, 1.0)
EMPTY = (0.1294, 0.1490, 0.1765, 1.0)
LEVELS = [
    (0.0549, 0.2667, 0.1608, 1.0),  # #0e4429
    (0.0, 0.4275, 0.1961, 1.0),     # #006d32
    (0.1490, 0.6510, 0.2549, 1.0),  # #26a641
    (0.2235, 0.8275, 0.3255, 1.0),  # #39d353
]
TXT = (0.5451, 0.5804, 0.6196, 1.0)

# --- Layout ---
CELL = 11
GAP = 2
STEP = CELL + GAP
LPAD = 45
TPAD = 55
RPAD = 20
BPAD = 35
W = LPAD + 53 * STEP - GAP + RPAD
H = TPAD + 7 * STEP - GAP + BPAD


# ---- Config & Data ----

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def get_token_from_keychain():
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-a", "ship-streak",
             "-s", "ship-streak-github", "-w"],
            capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except FileNotFoundError:
        pass
    return None


def save_token_to_keychain(token):
    subprocess.run(
        ["security", "add-generic-password", "-a", "ship-streak",
         "-s", "ship-streak-github", "-w", token, "-U"],
        capture_output=True, timeout=5)


def get_token_from_gh():
    try:
        r = subprocess.run(["gh", "auth", "token"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except FileNotFoundError:
        pass
    return None


def get_token():
    return get_token_from_keychain() or get_token_from_gh()


def resolve_credentials():
    """Returns (username, token) or (None, None) if incomplete."""
    cfg = load_config()
    username = cfg.get("username")
    token = get_token()

    # Try gh CLI for username if not in config
    if not username:
        try:
            r = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                username = r.stdout.strip()
                cfg["username"] = username
                save_config(cfg)
        except FileNotFoundError:
            pass

    # If gh provided a token but keychain is empty, cache it
    if token and not get_token_from_keychain():
        save_token_to_keychain(token)

    if username and token:
        return username, token
    return None, None


def fetch_year(token, username):
    q = """query($u:String!){user(login:$u){contributionsCollection{
      contributionCalendar{totalContributions weeks{contributionDays{
      contributionCount date weekday}}}}}}"""
    headers = {}
    if token:
        headers["Authorization"] = f"bearer {token}"
    r = requests.post(GRAPHQL_URL, json={"query": q, "variables": {"u": username}},
                      headers=headers, timeout=15)
    r.raise_for_status()
    d = r.json()
    if "errors" in d:
        raise RuntimeError(d["errors"])
    return d["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def calc_streak(weeks):
    by_date = {}
    for w in weeks:
        for d in w["contributionDays"]:
            by_date[d["date"]] = d["contributionCount"]

    dates = sorted(by_date.keys())
    if not dates:
        return 0, 0, 0

    today = dates[-1]
    today_count = by_date[today]

    streak = 0
    check = datetime.strptime(today, "%Y-%m-%d").date()
    if today_count == 0:
        check -= timedelta(days=1)
    while by_date.get(check.strftime("%Y-%m-%d"), 0) > 0:
        streak += 1
        check -= timedelta(days=1)

    longest = 0
    run = 0
    for d in dates:
        if by_date[d] > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    return today_count, streak, longest


def lvl(count):
    if count == 0: return 0
    if count <= 2: return 1
    if count <= 5: return 2
    if count <= 8: return 3
    return 4


# ---- View ----

class GraphView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(GraphView, self).initWithFrame_(frame)
        if self:
            self.cal = None
            self.total = 0
            self.today_count = 0
            self.streak = 0
            self.longest = 0
        return self

    def isFlipped(self):
        return True

    def drawRect_(self, rect):
        self._color(BG).setFill()
        bg = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(self.bounds(), 12, 12)
        bg.fill()
        self._color(BORDER).setStroke()
        bg.setLineWidth_(1)
        bg.stroke()

        if not self.cal:
            self._text("Loading...", LPAD, 25, 13, True)
            return

        weeks = self.cal["weeks"]
        self._text(f"{self.total} contributions in the last year", LPAD, 12, 13, True)

        icon = "\U0001f525" if self.today_count > 0 else "\u26a0\ufe0f"
        self._text(f"{icon} {self.streak}d streak  |  {self.today_count} today  |  best: {self.longest}d",
                   W - 280, 14, 11)

        prev = None
        for i, wk in enumerate(weeks):
            if not wk["contributionDays"]:
                continue
            m = datetime.strptime(wk["contributionDays"][0]["date"], "%Y-%m-%d").strftime("%b")
            if m != prev:
                self._text(m, LPAD + i * STEP, 36, 10)
                prev = m

        for row, lbl in {1: "Mon", 3: "Wed", 5: "Fri"}.items():
            self._text(lbl, 5, TPAD + row * STEP + 1, 9)

        for ci, wk in enumerate(weeks):
            for day in wk["contributionDays"]:
                x = LPAD + ci * STEP
                y = TPAD + day["weekday"] * STEP
                lv = lvl(day["contributionCount"])
                c = EMPTY if lv == 0 else LEVELS[lv - 1]
                self._color(c).setFill()
                NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    NSRect(NSPoint(x, y), NSSize(CELL, CELL)), 2, 2).fill()

        ly = H - 22
        lx = W - 175
        self._text("Less", lx, ly + 1, 9)
        lx += 30
        for c in [EMPTY] + LEVELS:
            self._color(c).setFill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSRect(NSPoint(lx, ly), NSSize(10, 10)), 2, 2).fill()
            lx += 14
        self._text("More", lx + 4, ly + 1, 9)

    @objc.python_method
    def _color(self, rgba):
        return NSColor.colorWithCalibratedRed_green_blue_alpha_(*rgba)

    @objc.python_method
    def _text(self, s, x, y, size, bold=False):
        f = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
        a = NSAttributedString.alloc().initWithString_attributes_(s, {
            NSForegroundColorAttributeName: self._color(TXT),
            NSFontAttributeName: f,
        })
        a.drawAtPoint_(NSPoint(x, y))

    def menuForEvent_(self, event):
        menu = NSMenu.alloc().init()
        ctrl = self.window().delegate()
        items = [
            ("Refresh Now", "refresh:"),
            ("Open GitHub Profile", "openProfile:"),
            None,
            ("Send to Back" if ctrl.is_floating else "Bring to Front", "toggleFloat:"),
            ("Hide Widget", "toggleWidget:"),
            None,
            ("Quit Ship Streak", "quit:"),
        ]
        for entry in items:
            if entry is None:
                menu.addItem_(NSMenuItem.separatorItem())
            else:
                title, sel = entry
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, sel, "")
                item.setTarget_(ctrl)
                menu.addItem_(item)
        return menu

    def triggerRedraw_(self, _):
        self.setNeedsDisplay_(True)


# ---- Controller ----

class AppController(NSObject):
    def init(self):
        self = objc.super(AppController, self).init()
        if self:
            self.graph_view = None
            self.widget_window = None
            self.status_item = None
            self.username = ""
            self.is_floating = True
            self.widget_visible = True
            self._toggle_widget_item = None
            self._toggle_float_item = None
        return self

    @objc.python_method
    def setup(self, window, view, username):
        self.widget_window = window
        self.graph_view = view
        self.username = username
        self._setup_status_bar()

    @objc.python_method
    def _setup_status_bar(self):
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength)
        self.status_item.button().setTitle_("SS")

        menu = NSMenu.alloc().init()
        self._toggle_widget_item = self._menu_item(menu, "Hide Widget", "toggleWidget:")
        self._toggle_float_item = self._menu_item(menu, "Send to Back", "toggleFloat:")
        menu.addItem_(NSMenuItem.separatorItem())
        self._menu_item(menu, "Refresh", "refresh:")
        self._menu_item(menu, "Open GitHub Profile", "openProfile:")
        menu.addItem_(NSMenuItem.separatorItem())
        self._menu_item(menu, "Quit Ship Streak", "quit:")
        self.status_item.setMenu_(menu)

    @objc.python_method
    def _menu_item(self, menu, title, selector):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, "")
        item.setTarget_(self)
        menu.addItem_(item)
        return item

    def refresh_(self, _):
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def toggleWidget_(self, _):
        if self.widget_visible:
            self.widget_window.orderOut_(None)
            self.widget_visible = False
        else:
            self.widget_window.makeKeyAndOrderFront_(None)
            self.widget_visible = True
        self._sync_menu_titles()

    def toggleFloat_(self, _):
        if self.is_floating:
            self.widget_window.setLevel_(DESKTOP_LEVEL)
            self.is_floating = False
        else:
            self.widget_window.setLevel_(FLOATING_LEVEL)
            self.widget_window.orderFront_(None)
            self.is_floating = True
        self._sync_menu_titles()

    def openProfile_(self, _):
        subprocess.Popen(["open", f"https://github.com/{self.username}"])

    def quit_(self, _):
        NSApplication.sharedApplication().terminate_(None)

    def updateMenuBar_(self, _):
        if not self.status_item:
            return
        v = self.graph_view
        if v and v.today_count > 0:
            self.status_item.button().setTitle_(f"\U0001f525 {v.streak}")
        elif v:
            self.status_item.button().setTitle_(f"\u26a0\ufe0f {v.streak}")

    @objc.python_method
    def _sync_menu_titles(self):
        if self._toggle_widget_item:
            self._toggle_widget_item.setTitle_(
                "Hide Widget" if self.widget_visible else "Show Widget")
        if self._toggle_float_item:
            self._toggle_float_item.setTitle_(
                "Send to Back" if self.is_floating else "Bring to Front")

    @objc.python_method
    def _do_refresh(self):
        try:
            token = get_token()
            cal = fetch_year(token, self.username)
            tc, st, lg = calc_streak(cal["weeks"])
            v = self.graph_view
            v.cal = cal
            v.total = cal["totalContributions"]
            v.today_count = tc
            v.streak = st
            v.longest = lg
            v.performSelectorOnMainThread_withObject_waitUntilDone_(
                "triggerRedraw:", None, False)
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "updateMenuBar:", None, False)
        except Exception as e:
            print(f"Refresh error: {e}", file=sys.stderr)


# ---- Setup Window ----

class SetupController(NSObject):
    def init(self):
        self = objc.super(SetupController, self).init()
        if self:
            self.window = None
            self.username_field = None
            self.token_field = None
            self.status_label = None
            self.connect_btn = None
            self.on_complete = None
        return self

    @objc.python_method
    def show(self, on_complete):
        self.on_complete = on_complete
        _refs.append(self)

        w = 440
        h = 340
        screen = NSScreen.mainScreen().visibleFrame()
        x = screen.origin.x + (screen.size.width - w) / 2
        y = screen.origin.y + (screen.size.height - h) / 2

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSRect(NSPoint(x, y), NSSize(w, h)),
            1 | 4,  # titled + closable
            NSBackingStoreBuffered, False)
        self.window.setTitle_("Ship Streak")
        self.window.setDelegate_(self)

        content = self.window.contentView()
        pad = 30

        # Header
        header = NSTextField.labelWithString_("Welcome to Ship Streak")
        header.setFont_(NSFont.boldSystemFontOfSize_(18))
        header.setFrame_(NSRect(NSPoint(pad, h - 50), NSSize(w - 2 * pad, 24)))
        content.addSubview_(header)

        # Subtitle
        sub = NSTextField.labelWithString_("Track your GitHub contribution streak on your desktop.")
        sub.setFont_(NSFont.systemFontOfSize_(13))
        sub.setTextColor_(NSColor.secondaryLabelColor())
        sub.setFrame_(NSRect(NSPoint(pad, h - 75), NSSize(w - 2 * pad, 18)))
        content.addSubview_(sub)

        # Username label
        ulbl = NSTextField.labelWithString_("GitHub Username")
        ulbl.setFont_(NSFont.systemFontOfSize_(12))
        ulbl.setFrame_(NSRect(NSPoint(pad, h - 110), NSSize(200, 16)))
        content.addSubview_(ulbl)

        # Username field
        self.username_field = NSTextField.alloc().initWithFrame_(
            NSRect(NSPoint(pad, h - 135), NSSize(w - 2 * pad, 24)))
        self.username_field.setPlaceholderString_("e.g. octocat")
        content.addSubview_(self.username_field)

        # Token label
        tlbl = NSTextField.labelWithString_("Personal Access Token")
        tlbl.setFont_(NSFont.systemFontOfSize_(12))
        tlbl.setFrame_(NSRect(NSPoint(pad, h - 165), NSSize(200, 16)))
        content.addSubview_(tlbl)

        # Token field (secure)
        self.token_field = NSSecureTextField.alloc().initWithFrame_(
            NSRect(NSPoint(pad, h - 190), NSSize(w - 2 * pad, 24)))
        self.token_field.setPlaceholderString_("ghp_...")
        content.addSubview_(self.token_field)

        # Help text
        help_lbl = NSTextField.labelWithString_("No special permissions needed. A classic token with no scopes works.")
        help_lbl.setFont_(NSFont.systemFontOfSize_(11))
        help_lbl.setTextColor_(NSColor.tertiaryLabelColor())
        help_lbl.setFrame_(NSRect(NSPoint(pad, h - 212), NSSize(w - 2 * pad, 14)))
        content.addSubview_(help_lbl)

        # Create Token button
        token_btn = NSButton.alloc().initWithFrame_(
            NSRect(NSPoint(pad, h - 240), NSSize(180, 24)))
        token_btn.setTitle_("Create Token on GitHub")
        token_btn.setBezelStyle_(NSBezelStyleRounded)
        token_btn.setTarget_(self)
        token_btn.setAction_("openTokenPage:")
        content.addSubview_(token_btn)

        # Status label
        self.status_label = NSTextField.labelWithString_("")
        self.status_label.setFont_(NSFont.systemFontOfSize_(12))
        self.status_label.setTextColor_(NSColor.systemRedColor())
        self.status_label.setFrame_(NSRect(NSPoint(pad, h - 270), NSSize(w - 2 * pad, 18)))
        content.addSubview_(self.status_label)

        # Connect button
        self.connect_btn = NSButton.alloc().initWithFrame_(
            NSRect(NSPoint(w - pad - 100, 15), NSSize(100, 32)))
        self.connect_btn.setTitle_("Connect")
        self.connect_btn.setBezelStyle_(NSBezelStyleRounded)
        self.connect_btn.setKeyEquivalent_("\r")
        self.connect_btn.setTarget_(self)
        self.connect_btn.setAction_("connect:")
        content.addSubview_(self.connect_btn)

        # Quit button
        quit_btn = NSButton.alloc().initWithFrame_(
            NSRect(NSPoint(pad, 15), NSSize(80, 32)))
        quit_btn.setTitle_("Quit")
        quit_btn.setBezelStyle_(NSBezelStyleRounded)
        quit_btn.setTarget_(self)
        quit_btn.setAction_("quitApp:")
        content.addSubview_(quit_btn)

        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def openTokenPage_(self, _):
        webbrowser.open("https://github.com/settings/tokens/new?description=Ship+Streak")

    def quitApp_(self, _):
        NSApplication.sharedApplication().terminate_(None)

    def windowWillClose_(self, _):
        NSApplication.sharedApplication().terminate_(None)

    def connect_(self, _):
        username = str(self.username_field.stringValue()).strip()
        token = str(self.token_field.stringValue()).strip()

        if not username:
            self.status_label.setStringValue_("Enter your GitHub username.")
            return
        if not token:
            self.status_label.setStringValue_("Enter your personal access token.")
            return

        self.connect_btn.setEnabled_(False)
        self.status_label.setTextColor_(NSColor.secondaryLabelColor())
        self.status_label.setStringValue_("Connecting...")

        threading.Thread(target=self._validate, args=(username, token), daemon=True).start()

    @objc.python_method
    def _validate(self, username, token):
        try:
            fetch_year(token, username)
            # Save credentials
            save_token_to_keychain(token)
            cfg = load_config()
            cfg["username"] = username
            save_config(cfg)
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "onSuccess:", username, False)
        except Exception as e:
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "onFailure:", str(e), False)

    def onSuccess_(self, username):
        self.window.setDelegate_(None)  # prevent windowWillClose_ from terminating
        self.window.close()
        if self.on_complete:
            self.on_complete(str(username))

    def onFailure_(self, error):
        self.status_label.setTextColor_(NSColor.systemRedColor())
        self.status_label.setStringValue_("Invalid username or token.")
        self.connect_btn.setEnabled_(True)


# ---- Widget Creation ----

def create_widget(app, username):
    screen = NSScreen.mainScreen().visibleFrame()
    x = screen.origin.x + screen.size.width - W - 30
    y = screen.origin.y + 30

    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSRect(NSPoint(x, y), NSSize(W, H)), 0, NSBackingStoreBuffered, False)
    win.setLevel_(FLOATING_LEVEL)
    win.setOpaque_(False)
    win.setBackgroundColor_(NSColor.clearColor())
    win.setHasShadow_(True)
    win.setMovableByWindowBackground_(True)
    win.setCollectionBehavior_(1 | 16)

    view = GraphView.alloc().initWithFrame_(
        NSRect(NSPoint(0, 0), NSSize(W, H)))
    win.setContentView_(view)

    ctrl = AppController.alloc().init()
    ctrl.setup(win, view, username)
    win.setDelegate_(ctrl)
    win.makeKeyAndOrderFront_(None)
    _refs.append(ctrl)

    NSWorkspace.sharedWorkspace().notificationCenter().addObserver_selector_name_object_(
        ctrl, "refresh:", "NSWorkspaceDidWakeNotification", None)

    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        REFRESH_INTERVAL, ctrl, "refresh:", None, True)

    ctrl.refresh_(None)


# ---- Main ----

def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(1)  # accessory: no dock icon, can show windows

    username, token = resolve_credentials()

    if username and token:
        create_widget(app, username)
    else:
        setup = SetupController.alloc().init()
        _refs.append(setup)
        setup.show(lambda u: create_widget(app, u))

    app.run()


if __name__ == "__main__":
    main()
