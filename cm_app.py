"""
Bulk certificate mailer - the companion to Meraki.

Reads the same CSV/Excel source file Meraki used, finds each person's
generated certificate (Name_CertificateID.pdf/png/jpg) in a folder, and emails
it to them through Gmail (SMTP + app password), in a background thread with
progress, cancel, a sent-log that prevents duplicate emails, and a final
summary with retry/export.

This is the entry point: it assembles the app class from the feature mixins.

    cm_constants.py     app name (ONE constant), paths, limits, header guesses
    cm_themes.py        THEMES (replace with a copy of Meraki's mck_themes.py)
    cm_utils.py         pure helpers: filenames, file reading, email check,
                        certificate matching, DPAPI secret storage
    cm_sentlog.py       sidecar log of who was already emailed
    cm_richtext.py      rich-text editor widget + runs -> HTML / plain text
    cm_mail.py          message building, Gmail SMTP, batch runner
    cm_dnd.py           drag-and-drop (tkinterdnd2)
    cm_core.py          init, splash, settings persistence
    cm_modal.py         modal-dialog attention + exit confirmation
    cm_theming.py       theme application
    cm_dialogs.py       Settings, first-run prompt, How to Use
    cm_widgets.py       section / toggle builders
    cm_upload_screen.py upload gate + Recipients/Compose tabs
    cm_source_view.py   recipients grid + row selection
    cm_loading.py       load source file, certificates folder, row analysis
    cm_compose.py       Compose tab (subject, message, footer picker)
    cm_footer.py        Footer tab (footer library: edit, live preview, save/revert/delete)
    cm_send.py          send flow + summary
    cm_build_ui.py      main window layout

Run with:  python cm_app.py
"""

import sys

from cm_constants import APP_USER_MODEL_ID
from cm_dnd import AppBase
from cm_core import CoreMixin
from cm_modal import ModalMixin
from cm_theming import ThemingMixin
from cm_dialogs import DialogsMixin
from cm_widgets import WidgetsMixin
from cm_upload_screen import UploadScreenMixin
from cm_source_view import SourceViewMixin
from cm_loading import LoadingMixin
from cm_compose import ComposeMixin
from cm_footer import FooterMixin
from cm_send import SendMixin
from cm_build_ui import BuildUiMixin


# CoreMixin (which defines __init__) must come BEFORE AppBase (tk.Tk): Tk's own
# __init__ doesn't call super().__init__(), so if AppBase came first the mixin
# __init__ would never run (same constraint as Meraki's mck_app.py).
class MailerApp(
    CoreMixin,
    AppBase,
    ModalMixin,
    ThemingMixin,
    DialogsMixin,
    WidgetsMixin,
    UploadScreenMixin,
    SourceViewMixin,
    LoadingMixin,
    ComposeMixin,
    FooterMixin,
    SendMixin,
    BuildUiMixin,
):
    pass


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        import ctypes
        # Own taskbar identity, so it doesn't group with Meraki or show Python's icon.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    MailerApp().mainloop()
