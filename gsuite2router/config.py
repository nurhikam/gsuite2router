"""Configuration constants, timing profiles, browser detection, and config file management."""

import os
import sys
import json

# ============================================================
# DEFAULTS
# ============================================================
DEFAULT_ROUTER_URL = "http://localhost:20128"
DEFAULT_ROUTER_PASSWORD = "123456"
DEFAULT_REDIRECT_URI = "http://localhost:20128/callback"
DEFAULT_AKUN_FILE = "akun.txt"
DEFAULT_DELAY = 3

# ============================================================
# CONFIG FILE
# ============================================================
CONFIG_FILE = ".gs2router.json"


def get_config_path():
    """Get config file path in CWD."""
    return os.path.join(os.getcwd(), CONFIG_FILE)


def load_config():
    """Load config from file. Returns dict or empty dict if not found."""
    path = get_config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_config(config):
    """Save config to file."""
    path = get_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"Config saved to {path}")


def get_config_value(key, cli_value, default):
    """Get value: CLI arg > config file > default."""
    if cli_value is not None:
        return cli_value
    config = load_config()
    if key in config:
        return config[key]
    return default


# ============================================================
# TIMING PROFILES
# ============================================================
TIMING = {
    "fast": {
        "google_initial": 1,
        "after_email_input": 0.5,
        "after_email_next": 2,
        "password_timeout": 8,
        "after_pw_input": 0.5,
        "after_pw_next": 2,
        "step_loop_wait": 1,
        "tos_button_timeout": 3,
        "after_tos_click": 1,
        "btn_find_timeout": 2,
        "after_consent_btn": 1,
        "after_allow": 1,
        "no_btn_wait": 2,
        "redirect_wait": 2,
        "after_success": 1,
    },
    "normal": {
        "google_initial": 3,
        "after_email_input": 1,
        "after_email_next": 4,
        "password_timeout": 15,
        "after_pw_input": 1,
        "after_pw_next": 4,
        "step_loop_wait": 2,
        "tos_button_timeout": 5,
        "after_tos_click": 2,
        "btn_find_timeout": 3,
        "after_consent_btn": 2,
        "after_allow": 3,
        "no_btn_wait": 3,
        "redirect_wait": 3,
        "after_success": 2,
    },
}

# ============================================================
# BROWSER DETECTION PATHS
# ============================================================
BROWSER_CANDIDATES = []

if sys.platform == "win32":
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    BROWSER_CANDIDATES = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(local_app_data, r"Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.join(local_app_data, r"BraveSoftware\Brave-Browser\Application\brave.exe"),
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    ]
elif sys.platform == "darwin":
    BROWSER_CANDIDATES = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ]
else:
    BROWSER_CANDIDATES = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ]

# ============================================================
# CHROME LAUNCH ARGS
# ============================================================
CHROME_ARGS = [
    "--start-maximized",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-sync",
    "--disable-translate",
    "--disable-infobars",
    "--disable-blink-features=AutomationControlled",
]

CHROME_IGNORE_DEFAULT_ARGS = ["--enable-automation"]
