# Bulk certificate mailer (companion to Meraki)

Reads the CSV/Excel file Meraki used, finds each person's generated certificate
(`Name_CertificateID.pdf/png/jpg`) in a folder, and emails it through Gmail.

## Setup
1. `pip install pillow openpyxl tkinterdnd2` (tkinterdnd2 is optional - browse-only without it).
2. Copy your Meraki `mck_themes.py` over `cm_themes.py` (same 12 themes), and copy
   `icons/ORIC.png` from Meraki into this app's `icons/` folder. `icons/app_icon.png`
   is a placeholder envelope - replace it with your own logo (optional `app_icon.ico` too).
3. **Name:** change `APP_NAME` in `cm_constants.py` - window title, toolbar, splash text,
   `%LOCALAPPDATA%\<name>\` folder and taskbar ID all follow. (Rename before first real use:
   a new name starts a fresh settings folder.)
4. Run: `python cm_app.py`

## Footers
Settings -> "Edit default footer" opens the **Footer** tab: editor on top, live preview below,
`<` `>` to move between saved footers (`>` on the last one starts a single new unsaved footer),
Save / Revert / Delete, and "Use this footer". The Compose tab has a picker for the footer to send.

## Fonts
The editors (Compose message and Footer tab) offer the fonts Gmail itself renders: Arial, Arial Black,
Arial Narrow, Comic Sans MS, Courier New, Garamond, Georgia, Tahoma, Times New Roman, Trebuchet MS,
Verdana. Gmail ignores web fonts, so these are the safe set; each is sent with a fallback stack. A font
only shows if the reader's device has it (otherwise their mail app substitutes a similar one).

## Gmail
Turn on 2-Step Verification on the sending account, create an app password at
myaccount.google.com/apppasswords, and enter it in Settings (or the first-run prompt).
It is stored encrypted with Windows DPAPI inside `settings.json`.

## Where things are stored (`%LOCALAPPDATA%\<APP_NAME>\`)
- `settings.json` - sender, encrypted app password, theme, saved footers (+ which one is in use), recent files.
- `sent_log.json` - who has been emailed (keyed by Certificate ID + address). Your source
  file is never modified.

## Tests
`python -m unittest test_cm_logic -v` (matching, email checks, rich text, SMTP batch logic
against a fake server; no network, no GUI).

## Build an .exe (PyInstaller, like Meraki)
`pyinstaller --onefile --windowed --collect-all tkinterdnd2 --add-data "icons;icons" cm_app.py`
