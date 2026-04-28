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
    NSBezelStyleRounded, NSGraphicsContext,
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
TPAD = 63
RPAD = 20
BPAD = 35
W = LPAD + 53 * STEP - GAP + RPAD
H = TPAD + 7 * STEP - GAP + BPAD


# ---- Theme Definitions ----

def _fire_icon(streak, today_count):
    return "\U0001f525" if today_count > 0 else "\u26a0\ufe0f"

def _barbie_icon(streak, today_count):
    if today_count == 0:
        return "\u26a0\ufe0f"
    if streak >= 365:
        return "\U0001f451"   # crown
    if streak >= 180:
        return "\U0001f48e"   # gem
    if streak >= 169:
        return "\U0001f9a9"   # flamingo
    if streak >= 45:
        return "\U0001f485"   # nail polish
    if streak >= 21:
        return "\U0001f496"   # sparkling heart
    if streak >= 11:
        return "\u2b50"       # star
    return "\u2728"           # sparkles

def _water_icon(streak, today_count):
    return "\U0001f4a7" if today_count > 0 else "\u26a0\ufe0f"

def _minesweeper_icon(streak, today_count):
    if today_count == 0:
        return "\U0001f4a3"   # bomb - you missed!
    if streak >= 100:
        return "\U0001f60e"   # sunglasses - legend
    if streak >= 30:
        return "\U0001f3c6"   # trophy - winning
    return "\U0001f642"       # smiley - the classic minesweeper face

THEME_ORDER = ["github_classic", "midnight_inferno", "malibu_dream", "ocean_drift", "minesweeper"]

THEMES = {
    "github_classic": {
        "name": "GitHub Classic",
        "bg": BG,
        "border": BORDER,
        "empty": EMPTY,
        "levels": LEVELS,
        "text": TXT,
        "cell_style": "solid",
        "streak_icon": _fire_icon,
    },
    "midnight_inferno": {
        "name": "Midnight Inferno",
        "bg": BG,
        "border": BORDER,
        "empty": EMPTY,
        "levels": [
            (0.80, 0.65, 0.10, 1.0),   # gold
            (0.90, 0.50, 0.05, 1.0),   # orange
            (0.85, 0.30, 0.05, 1.0),   # orange-red
            (0.70, 0.10, 0.15, 1.0),   # crimson
        ],
        "text": TXT,
        "cell_style": "emoji",
        "emoji_levels": ["\U0001f56f\ufe0f", "\U0001f525", "\U0001f4a5", "\u2604\ufe0f"],
        "streak_icon": _fire_icon,
    },
    "malibu_dream": {
        "name": "Malibu Dream",
        "bg": (0.10, 0.05, 0.10, 0.95),
        "border": (0.25, 0.10, 0.20, 1.0),
        "empty": (0.15, 0.08, 0.13, 1.0),
        "levels": [
            (0.85, 0.60, 0.70, 1.0),   # light pink
            (1.00, 0.41, 0.71, 1.0),   # hot pink
            (1.00, 0.08, 0.58, 1.0),   # deep pink
            (0.78, 0.08, 0.52, 1.0),   # medium violet red
        ],
        "text": (0.95, 0.75, 0.85, 1.0),
        "cell_style": "emoji",
        "emoji_levels": ["\U0001f60a", "\U0001f604", "\U0001f970", "\U0001f496"],
        "streak_icon": _barbie_icon,
    },
    "ocean_drift": {
        "name": "Ocean Drift",
        "bg": (0.02, 0.05, 0.15, 0.35),
        "border": (0.20, 0.35, 0.55, 0.50),
        "empty": (0.15, 0.25, 0.40, 0.30),
        "levels": [
            (0.53, 0.81, 0.92, 0.90),  # sky blue
            (0.40, 0.70, 0.90, 0.90),  # light blue
            (0.15, 0.45, 0.80, 0.90),  # strong blue
            (0.05, 0.25, 0.60, 0.95),  # deep blue
        ],
        "text": (0.92, 0.96, 1.0, 0.95),
        "cell_style": "water",
        "streak_icon": _water_icon,
    },
    "minesweeper": {
        "name": "Minesweeper",
        "bg": (0.75, 0.75, 0.75, 0.95),         # classic silver #C0C0C0
        "border": (0.50, 0.50, 0.50, 1.0),       # dark gray frame
        "empty": (0.75, 0.75, 0.75, 1.0),        # unrevealed base gray
        "levels": [
            (0.0, 0.0, 1.0, 1.0),                # 1 = blue
            (0.0, 0.5, 0.0, 1.0),                # 2 = dark green
            (1.0, 0.0, 0.0, 1.0),                # 3 = red
            (0.0, 0.0, 0.5, 1.0),                # 4 = dark blue
        ],
        "text": (0.15, 0.15, 0.15, 1.0),
        "cell_style": "minesweeper",
        "ms_highlight": (1.0, 1.0, 1.0, 1.0),   # white bevel top/left
        "ms_shadow": (0.50, 0.50, 0.50, 1.0),    # dark gray bevel bottom/right
        "ms_revealed": (0.72, 0.72, 0.72, 1.0),  # flat revealed cell
        "ms_grid": (0.50, 0.50, 0.50, 1.0),      # thin grid line on revealed
        "ms_led_bg": (0.05, 0.05, 0.05, 1.0),     # black LED background
        "ms_led_fg": (0.85, 0.0, 0.0, 1.0),        # red LED digits
        "ms_led_dim": (0.20, 0.0, 0.0, 1.0),       # dim red for "off" segments
        "streak_icon": _minesweeper_icon,
    },
}

_WATER_FILL = {1: 0.30, 2: 0.55, 3: 0.80, 4: 1.0}


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
            self.theme_key = "github_classic"
        return self

    def isFlipped(self):
        return True

    def drawRect_(self, rect):
        theme = THEMES[self.theme_key]

        self._color(theme["bg"]).setFill()
        bg = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(self.bounds(), 12, 12)
        bg.fill()
        self._color(theme["border"]).setStroke()
        bg.setLineWidth_(1)
        bg.stroke()

        if not self.cal:
            self._text("Loading...", LPAD, 25, 13, True)
            return

        weeks = self.cal["weeks"]

        if theme["cell_style"] == "minesweeper":
            # LED counter header - labels above boxes
            led_w = 56
            led_h = 24
            label_sz = 8
            label_y = 4
            led_y = label_y + label_sz + 2
            # Left side: total + streak
            self._ms_label("total", LPAD, label_y, led_w, label_sz)
            self._draw_led_number(self.total, LPAD, led_y, led_w, led_h)
            streak_x = LPAD + led_w + 16
            self._ms_label("streak", streak_x, label_y, led_w, label_sz)
            self._draw_led_number(self.streak, streak_x, led_y, led_w, led_h)
            # Right side: today + best
            best_x = W - RPAD - led_w
            self._ms_label("best", best_x, label_y, led_w, label_sz)
            self._draw_led_number(self.longest, best_x, led_y, led_w, led_h)
            today_x = best_x - led_w - 16
            self._ms_label("today", today_x, label_y, led_w, label_sz)
            self._draw_led_number(self.today_count, today_x, led_y, led_w, led_h)
        else:
            self._text(f"{self.total} contributions in the last year", LPAD, 12, 13, True)
            icon = theme["streak_icon"](self.streak, self.today_count)
            self._text(f"{icon} {self.streak}d streak  |  {self.today_count} today  |  best: {self.longest}d",
                       W - 280, 14, 11)

        prev = None
        month_y = 44 if theme["cell_style"] == "minesweeper" else 36
        last_drawn_x = -100
        for i, wk in enumerate(weeks):
            if not wk["contributionDays"]:
                continue
            m = datetime.strptime(wk["contributionDays"][0]["date"], "%Y-%m-%d").strftime("%b")
            cur_x = LPAD + i * STEP
            if m != prev and cur_x - last_drawn_x >= 3 * STEP:
                self._text(m, cur_x, month_y, 10)
                last_drawn_x = cur_x
                prev = m

        for row, lbl in {1: "Mon", 3: "Wed", 5: "Fri"}.items():
            self._text(lbl, 5, TPAD + row * STEP + 1, 9)

        for ci, wk in enumerate(weeks):
            for day in wk["contributionDays"]:
                x = LPAD + ci * STEP
                y = TPAD + day["weekday"] * STEP
                lv = lvl(day["contributionCount"])
                self._draw_cell(theme, x, y, lv)

        ly = H - 22
        lx = W - 175
        self._text("Less", lx, ly + 1, 9)
        lx += 30
        for i in range(5):
            self._draw_cell(theme, lx, ly, i, size=10)
            lx += 14
        self._text("More", lx + 4, ly + 1, 9)

    @objc.python_method
    def _color(self, rgba):
        return NSColor.colorWithCalibratedRed_green_blue_alpha_(*rgba)

    @objc.python_method
    def _draw_cell(self, theme, x, y, level, size=None):
        sz = size or CELL
        r = 2
        cell_rect = NSRect(NSPoint(x, y), NSSize(sz, sz))
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(cell_rect, r, r)

        if theme["cell_style"] == "minesweeper":
            bv = max(1, int(sz * 0.18))
            if level == 0:
                # Empty raised bevel (unrevealed tile)
                self._color(theme["empty"]).setFill()
                NSBezierPath.fillRect_(cell_rect)
                self._color(theme["ms_highlight"]).setFill()
                NSBezierPath.fillRect_(NSRect(NSPoint(x, y), NSSize(sz, bv)))
                NSBezierPath.fillRect_(NSRect(NSPoint(x, y), NSSize(bv, sz)))
                self._color(theme["ms_shadow"]).setFill()
                NSBezierPath.fillRect_(NSRect(NSPoint(x, y + sz - bv), NSSize(sz, bv)))
                NSBezierPath.fillRect_(NSRect(NSPoint(x + sz - bv, y), NSSize(bv, sz)))
            else:
                # Revealed tile with emoji based on level
                self._color(theme["ms_revealed"]).setFill()
                NSBezierPath.fillRect_(cell_rect)
                self._color(theme["ms_grid"]).setStroke()
                bp = NSBezierPath.bezierPathWithRect_(cell_rect)
                bp.setLineWidth_(0.5)
                bp.stroke()
                if level == 1:
                    # Blue "1" digit
                    num = "1"
                    font_sz = sz - 3
                    f = NSFont.boldSystemFontOfSize_(font_sz)
                    a = NSAttributedString.alloc().initWithString_attributes_(num, {
                        NSFontAttributeName: f,
                        NSForegroundColorAttributeName: self._color(theme["levels"][0]),
                    })
                    ts = a.size()
                    a.drawAtPoint_(NSPoint(x + (sz - ts.width) / 2, y + (sz - ts.height) / 2))
                else:
                    # 2=bomb, 3=flag, 4=smiley
                    _ms_emoji = {2: "\U0001f4a3", 3: "\U0001f6a9", 4: "\U0001f60a"}
                    emoji = _ms_emoji.get(level, "\U0001f4a3")
                    font_sz = sz - 2
                    f = NSFont.systemFontOfSize_(font_sz)
                    a = NSAttributedString.alloc().initWithString_attributes_(emoji, {
                        NSFontAttributeName: f,
                    })
                    es = a.size()
                    a.drawAtPoint_(NSPoint(x + (sz - es.width) / 2, y + (sz - es.height) / 2))
        elif theme["cell_style"] == "emoji":
            self._color(theme["empty"]).setFill()
            path.fill()
            if level > 0:
                emoji = theme["emoji_levels"][level - 1]
                font_sz = sz - 1
                f = NSFont.systemFontOfSize_(font_sz)
                a = NSAttributedString.alloc().initWithString_attributes_(emoji, {
                    NSFontAttributeName: f,
                })
                e_size = a.size()
                ex = x + (sz - e_size.width) / 2
                ey = y + (sz - e_size.height) / 2
                a.drawAtPoint_(NSPoint(ex, ey))
        elif theme["cell_style"] == "water":
            self._color(theme["border"]).setStroke()
            path.setLineWidth_(0.5)
            path.stroke()
            if level > 0:
                fill_frac = _WATER_FILL[level]
                fill_h = sz * fill_frac
                fill_rect = NSRect(NSPoint(x, y + sz - fill_h), NSSize(sz, fill_h))
                NSGraphicsContext.currentContext().saveGraphicsState()
                path.addClip()
                self._color(theme["levels"][level - 1]).setFill()
                NSBezierPath.fillRect_(fill_rect)
                NSGraphicsContext.currentContext().restoreGraphicsState()
        else:
            c = theme["empty"] if level == 0 else theme["levels"][level - 1]
            self._color(c).setFill()
            path.fill()

    @objc.python_method
    def _draw_led_number(self, value, x, y, width, height):
        """Draw a number in red LED style on a black recessed panel."""
        theme = THEMES[self.theme_key]
        # Black recessed background
        panel_rect = NSRect(NSPoint(x, y), NSSize(width, height))
        self._color(theme["ms_led_bg"]).setFill()
        NSBezierPath.fillRect_(panel_rect)
        # Sunken border: dark outer, lighter inner
        outer = NSBezierPath.bezierPathWithRect_(panel_rect)
        self._color((0.15, 0.15, 0.15, 1.0)).setStroke()
        outer.setLineWidth_(1.0)
        outer.stroke()
        inner_rect = NSRect(NSPoint(x + 1, y + 1), NSSize(width - 2, height - 2))
        inner = NSBezierPath.bezierPathWithRect_(inner_rect)
        self._color((0.25, 0.25, 0.25, 1.0)).setStroke()
        inner.setLineWidth_(0.5)
        inner.stroke()
        # Dim "888" behind for off-segment look
        dim_text = "888"
        font_sz = height - 6
        f = NSFont.monospacedDigitSystemFontOfSize_weight_(font_sz, 0.7)  # bold weight
        dim_a = NSAttributedString.alloc().initWithString_attributes_(dim_text, {
            NSFontAttributeName: f,
            NSForegroundColorAttributeName: self._color(theme["ms_led_dim"]),
        })
        ds = dim_a.size()
        dx = x + (width - ds.width) / 2
        dy = y + (height - ds.height) / 2
        dim_a.drawAtPoint_(NSPoint(dx, dy))
        # Actual number in bright red
        num_text = f"{int(value):03d}"
        num_a = NSAttributedString.alloc().initWithString_attributes_(num_text, {
            NSFontAttributeName: f,
            NSForegroundColorAttributeName: self._color(theme["ms_led_fg"]),
        })
        num_a.drawAtPoint_(NSPoint(dx, dy))

    @objc.python_method
    def _ms_label(self, text, x, y, width, size):
        """Draw a small centered gray label below an LED panel."""
        f = NSFont.systemFontOfSize_(size)
        a = NSAttributedString.alloc().initWithString_attributes_(text, {
            NSFontAttributeName: f,
            NSForegroundColorAttributeName: self._color((0.35, 0.35, 0.35, 1.0)),
        })
        ts = a.size()
        a.drawAtPoint_(NSPoint(x + (width - ts.width) / 2, y))

    @objc.python_method
    def _text(self, s, x, y, size, bold=False):
        theme = THEMES[self.theme_key]
        f = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
        a = NSAttributedString.alloc().initWithString_attributes_(s, {
            NSForegroundColorAttributeName: self._color(theme["text"]),
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
        ]
        for entry in items:
            if entry is None:
                menu.addItem_(NSMenuItem.separatorItem())
            else:
                title, sel = entry
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, sel, "")
                item.setTarget_(ctrl)
                menu.addItem_(item)

        theme_sub = NSMenu.alloc().initWithTitle_("Theme")
        for idx, key in enumerate(THEME_ORDER):
            t_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                THEMES[key]["name"], "switchTheme:", "")
            t_item.setTag_(idx)
            t_item.setTarget_(ctrl)
            if key == self.theme_key:
                t_item.setState_(1)
            theme_sub.addItem_(t_item)
        theme_holder = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Theme", None, "")
        theme_holder.setSubmenu_(theme_sub)
        menu.addItem_(theme_holder)

        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit Ship Streak", "quit:", "")
        quit_item.setTarget_(ctrl)
        menu.addItem_(quit_item)
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
            self._theme_items = []
        return self

    @objc.python_method
    def setup(self, window, view, username):
        self.widget_window = window
        self.graph_view = view
        self.username = username
        self._setup_status_bar()
        self._sync_theme_checks()

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

        self._theme_items = []
        theme_sub = NSMenu.alloc().initWithTitle_("Theme")
        for idx, key in enumerate(THEME_ORDER):
            t_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                THEMES[key]["name"], "switchTheme:", "")
            t_item.setTag_(idx)
            t_item.setTarget_(self)
            theme_sub.addItem_(t_item)
            self._theme_items.append(t_item)
        theme_holder = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Theme", None, "")
        theme_holder.setSubmenu_(theme_sub)
        menu.addItem_(theme_holder)

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
        if v:
            theme = THEMES[v.theme_key]
            icon = theme["streak_icon"](v.streak, v.today_count)
            self.status_item.button().setTitle_(f"{icon} {v.streak}")

    @objc.python_method
    def _sync_menu_titles(self):
        if self._toggle_widget_item:
            self._toggle_widget_item.setTitle_(
                "Hide Widget" if self.widget_visible else "Show Widget")
        if self._toggle_float_item:
            self._toggle_float_item.setTitle_(
                "Send to Back" if self.is_floating else "Bring to Front")

    def switchTheme_(self, sender):
        idx = sender.tag()
        key = THEME_ORDER[idx]
        self.graph_view.theme_key = key
        cfg = load_config()
        cfg["theme"] = key
        save_config(cfg)
        self.graph_view.setNeedsDisplay_(True)
        self.updateMenuBar_(None)
        self._sync_theme_checks()

    @objc.python_method
    def _sync_theme_checks(self):
        current = self.graph_view.theme_key if self.graph_view else "github_classic"
        for item in self._theme_items:
            idx = item.tag()
            item.setState_(1 if THEME_ORDER[idx] == current else 0)

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
    view.theme_key = load_config().get("theme", "github_classic")
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
