"""Fixed configuration for the certificate mailer: the app name (ONE place
to change it), file locations, limits, header-guess lists, and theme data."""

import os
import re
import sys

from cm_themes import THEMES as themes_dictionary

# ---------------------------------------------------------------------------
# App identity - change APP_NAME here and the window title, toolbar brand,
# splash text, %LOCALAPPDATA% folder and taskbar ID all follow.
# (Changing it later starts a fresh settings folder under the new name.)
# ---------------------------------------------------------------------------
APP_NAME = "Segno"
APP_SUBTITLE = "BULK CERTIFICATE MAILER"
APP_FULL_TITLE = f"{APP_NAME} - Bulk Certificate Mailer"
APP_CREDIT_TEXT = "Developed by Muhammad Bilal Khan for ORIC, UoK"
SPLASH_CREDIT_TEXT = (f"{APP_NAME} by Office of Research, Innovation and "
                      f"Commercialization, University of Karachi")
APP_USER_MODEL_ID = "oric." + re.sub(r"[^a-z0-9]", "", APP_NAME.lower()) + ".certmailer.1.0"
GITHUB_ISSUES_URL = "https://github.com/mbilalkhan704/bulk-certificates-generator-ORIC-UOK/issues"
APP_PASSWORD_URL = "https://myaccount.google.com/apppasswords"


def resource_path(relative_path: str) -> str:
    """Absolute path to a bundled resource (source run or PyInstaller onefile)."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def _safe_folder_name(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name).strip() or "CertMailer"


def get_appdata_dir(app_name=None) -> str:
    """Per-user writable folder, a sibling of Meraki's %LOCALAPPDATA%\\Meraki.
    CM_APPDATA_DIR overrides it (used by the tests)."""
    path = os.environ.get("CM_APPDATA_DIR")
    if not path:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, _safe_folder_name(app_name or APP_NAME))
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


APPDATA_DIR = get_appdata_dir()
SETTINGS_PATH = os.path.join(APPDATA_DIR, "settings.json")
SENT_LOG_PATH = os.path.join(APPDATA_DIR, "sent_log.json")

ORIC_LOGO_FILE = resource_path("icons/ORIC.png")
APP_ICON_PNG = resource_path("icons/app_icon.png")
APP_ICON_ICO = resource_path("icons/app_icon.ico")

# ---------------------------------------------------------------------------
# Matching / source-file conventions (must mirror Meraki)
# ---------------------------------------------------------------------------
CERT_ID_COLUMN = "Certificate ID"
CERT_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg")   # priority order
NAME_HEADER_GUESSES = ("name", "full name", "fullname", "participant", "student name")
EMAIL_HEADER_GUESSES = ("email", "e-mail", "email address", "e-mail address",
                        "mail", "email id", "emailid", "email_address")
ID_MATCH_MIN_NAME_SIMILARITY = 0.75   # safety net for the "matched by ID" fallback

# ---------------------------------------------------------------------------
# Gmail sending
# ---------------------------------------------------------------------------
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587                        # STARTTLS
SMTP_TIMEOUT = 30
GMAIL_MAX_MESSAGE_BYTES = 25 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 18 * 1024 * 1024   # base64 inflates ~33%, leave headroom
DAILY_LIMIT_FREE_GMAIL = 500              # recipients / rolling 24h
DAILY_LIMIT_WORKSPACE = 2000
DEFAULT_SEND_DELAY = 1.5                  # seconds between emails
MAX_CONSECUTIVE_CONNECTION_FAILURES = 3

MAX_RECENT_FILES = 8
MAX_REMEMBERED_FOLDERS = 25

# ---------------------------------------------------------------------------
# Rich text / email look
# ---------------------------------------------------------------------------
EMAIL_BASE_FONT_PX = 14
EMAIL_FONT_FAMILY_CSS = "Arial, Helvetica, sans-serif"
FONT_SIZES_PX = [10, 11, 12, 13, 14, 16, 18, 20, 24, 28, 32]
NAME_PLACEHOLDER = "{name}"

# Fonts Gmail itself renders (it ignores web fonts and falls back to a system font), each with
# a fallback stack so other mail apps degrade sensibly. Arial is the default, so a run with
# no explicit font writes no font-family at all.
DEFAULT_EMAIL_FONT = "Arial"
EMAIL_FONTS = [
    ("Arial", "Arial, Helvetica, sans-serif"),
    ("Arial Black", "'Arial Black', Gadget, sans-serif"),
    ("Arial Narrow", "'Arial Narrow', Arial, sans-serif"),
    ("Comic Sans MS", "'Comic Sans MS', 'Comic Sans', cursive"),
    ("Courier New", "'Courier New', Courier, monospace"),
    ("Garamond", "Garamond, 'Times New Roman', serif"),
    ("Georgia", "Georgia, 'Times New Roman', serif"),
    ("Tahoma", "Tahoma, Geneva, sans-serif"),
    ("Times New Roman", "'Times New Roman', Times, serif"),
    ("Trebuchet MS", "'Trebuchet MS', Helvetica, sans-serif"),
    ("Verdana", "Verdana, Geneva, sans-serif"),
]

# ---------------------------------------------------------------------------
# Splash + themes
# ---------------------------------------------------------------------------
SPLASH_BG = "#0f1021"
SPLASH_PALETTE = ["#ff6b6b", "#feca57", "#1dd1a1", "#54a0ff", "#c56cf0", "#ff9ff3"]
SPLASH_DURATION_MS = 5000
SPLASH_LOGO_SIZE = 150

THEMES = themes_dictionary
DEFAULT_THEME = "Light"
