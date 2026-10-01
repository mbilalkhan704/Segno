"""Email building and Gmail SMTP sending (no Tk): message rendering, error
classification, a reusable SMTP connection, the batch runner used by the
background worker, and the credentials test."""

import mimetypes
import os
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate

from cm_constants import (
    SMTP_HOST, SMTP_PORT, SMTP_TIMEOUT, MAX_ATTACHMENT_BYTES,
    MAX_CONSECUTIVE_CONNECTION_FAILURES, EMAIL_BASE_FONT_PX, EMAIL_FONT_FAMILY_CSS,
)
from cm_richtext import (
    NAME_TOKEN_RE, substitute_name, runs_to_html, runs_to_plain, has_visible_text,
)

FATAL_KINDS = ("auth", "quota")
_QUOTA_RE = re.compile(r"5\.4\.5|daily|quota|sending limit|rate limit exceeded", re.I)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_email(subject_template, message_runs, footer_runs, name):
    """Return (subject, plain_text, html) for one recipient. {name} is
    substituted everywhere; the name is HTML-escaped automatically because
    substitution happens before HTML rendering."""
    subject = NAME_TOKEN_RE.sub(lambda m: name, subject_template or "")
    subject = re.sub(r"[\r\n]+", " ", subject).strip()

    msg_runs = substitute_name(message_runs, name)
    foot_runs = substitute_name(footer_runs, name)
    plain = runs_to_plain(msg_runs).rstrip()
    body = runs_to_html(msg_runs)
    if has_visible_text(foot_runs):
        plain += "\n\n" + runs_to_plain(foot_runs).strip()
        body += "<br><br>" + runs_to_html(foot_runs)
    html_doc = (f'<html><body><div style="font-family:{EMAIL_FONT_FAMILY_CSS};'
                f'font-size:{EMAIL_BASE_FONT_PX}px;line-height:1.5;color:#222222;">'
                f'{body}</div></body></html>')
    return subject, plain, html_doc


def build_message(sender_email, sender_name, to_email, subject, plain, html_body, attachment_path=None):
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, sender_email)) if sender_name else sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(plain or " ")
    msg.add_alternative(html_body, subtype="html")
    if attachment_path:
        ctype, _enc = mimetypes.guess_type(attachment_path)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        with open(attachment_path, "rb") as f:
            data = f.read()
        msg.add_attachment(data, maintype=maintype, subtype=subtype,
                           filename=os.path.basename(attachment_path))
    return msg


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
def _server_text(exc):
    err = getattr(exc, "smtp_error", None)
    if isinstance(err, bytes):
        err = err.decode("utf-8", "replace")
    code = getattr(exc, "smtp_code", None)
    return f"{code} {err}".strip() if code or err else str(exc)


def classify_exception(exc):
    """Map an exception to (kind, friendly_text). Kinds: auth, quota, size,
    recipient, sender, temporary, connection, other."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "auth", ("Gmail rejected the sign-in - check the sender address and app password. "
                        + _server_text(exc))
    if isinstance(exc, smtplib.SMTPException) and _QUOTA_RE.search(_server_text(exc) + " " + str(exc)):
        return "quota", "Gmail's daily sending limit was reached. " + _server_text(exc)
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        detail = "; ".join(f"{a}: {c} {m.decode('utf-8', 'replace') if isinstance(m, bytes) else m}"
                           for a, (c, m) in exc.recipients.items())
        return "recipient", "Address rejected - " + detail
    if isinstance(exc, smtplib.SMTPSenderRefused):
        if exc.smtp_code == 552 or "size" in _server_text(exc).lower():
            return "size", "Message too large for Gmail. " + _server_text(exc)
        return "sender", "Sender refused. " + _server_text(exc)
    if isinstance(exc, smtplib.SMTPResponseException):
        code, text = exc.smtp_code, _server_text(exc)
        if code == 552 or "too large" in text.lower():
            return "size", "Message too large for Gmail. " + text
        if 400 <= code < 500:
            return "temporary", "Temporary Gmail error (try again later). " + text
        return "other", text
    if isinstance(exc, (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
                        ConnectionError, TimeoutError, socket.timeout, ssl.SSLError, OSError)):
        return "connection", f"Connection problem: {exc}"
    return "other", str(exc) or exc.__class__.__name__


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
class MailSender:
    """One reusable authenticated SMTP session for a whole batch."""

    def __init__(self, email, password, host=SMTP_HOST, port=SMTP_PORT,
                 timeout=SMTP_TIMEOUT, smtp_factory=None):
        self.email, self.password = email, password
        self.host, self.port, self.timeout = host, port, timeout
        self._factory = smtp_factory or smtplib.SMTP
        self.server = None

    def connect(self):
        self.close()
        server = self._factory(self.host, self.port, timeout=self.timeout)
        try:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(self.email, self.password)
        except Exception:
            try:
                server.close()
            except Exception:
                pass
            raise
        self.server = server

    def send(self, msg):
        try:
            self.server.send_message(msg)
        except (smtplib.SMTPServerDisconnected, ConnectionError, TimeoutError, socket.timeout):
            self.connect()                         # one transparent reconnect
            self.server.send_message(msg)

    def close(self):
        if self.server is not None:
            try:
                self.server.quit()
            except Exception:
                try:
                    self.server.close()
                except Exception:
                    pass
            self.server = None


def validate_smtp_credentials(email, password, timeout=12, smtp_factory=None):
    """('valid', None) | ('invalid', msg) | ('error', msg) - same three-way
    result as Meraki's API-key check: a network problem is NOT 'invalid'."""
    sender = MailSender(email, password, timeout=timeout, smtp_factory=smtp_factory)
    try:
        sender.connect()
        return "valid", None
    except smtplib.SMTPAuthenticationError as exc:
        return "invalid", _server_text(exc)
    except Exception as exc:
        return "error", str(exc)
    finally:
        sender.close()


# ---------------------------------------------------------------------------
# Batch runner (runs on the worker thread; talks to the UI only via emit())
# ---------------------------------------------------------------------------
def run_batch(jobs, cfg, render, emit, cancel, delay, smtp_factory=None):
    """jobs: dicts with row, name, email, cert_path, (test, subject_prefix).
    Events: ('sent',job) ('failed',job,kind,msg) ('skipped',job,reason)
    ('fatal',kind,msg) ('cancelled',) ('progress',done,total) ('done',)."""
    total, done = len(jobs), 0

    def tick():
        nonlocal done
        done += 1
        emit(("progress", done, total))

    ready = []
    for j in jobs:                                   # cheap pre-checks, no network yet
        path = j.get("cert_path")
        if path:
            try:
                size = os.path.getsize(path)
            except OSError as exc:
                emit(("failed", j, "file", f"Can't read the certificate file: {exc}"))
                tick()
                continue
            if size > MAX_ATTACHMENT_BYTES:
                emit(("failed", j, "size", f"Certificate file is {size / 1048576:.1f} MB - "
                                            f"too large to attach (limit ~{MAX_ATTACHMENT_BYTES // 1048576} MB)."))
                tick()
                continue
        ready.append(j)

    def skip_rest(start, reason):
        for k in ready[start:]:
            emit(("skipped", k, reason))
            tick()

    sender = MailSender(cfg["email"], cfg["password"], smtp_factory=smtp_factory)
    try:
        if not ready:
            return
        try:
            sender.connect()
        except Exception as exc:
            kind, text = classify_exception(exc)
            emit(("fatal", kind, text))
            skip_rest(0, "not attempted")
            return
        consecutive_conn = 0
        for idx, j in enumerate(ready):
            if cancel.is_set():
                emit(("cancelled",))
                skip_rest(idx, "cancelled")
                return
            try:
                subject, plain, html_body = render(j["name"])
                subject = (j.get("subject_prefix") or "") + subject
                msg = build_message(cfg["email"], cfg.get("sender_name", ""), j["email"],
                                    subject, plain, html_body, j.get("cert_path"))
                sender.send(msg)
            except Exception as exc:
                kind, text = classify_exception(exc)
                emit(("failed", j, kind, text))
                tick()
                if kind in FATAL_KINDS:
                    emit(("fatal", kind, text))
                    skip_rest(idx + 1, "not attempted")
                    return
                consecutive_conn = consecutive_conn + 1 if kind == "connection" else 0
                if consecutive_conn >= MAX_CONSECUTIVE_CONNECTION_FAILURES:
                    emit(("fatal", "connection", text))
                    skip_rest(idx + 1, "not attempted")
                    return
            else:
                consecutive_conn = 0
                emit(("sent", j))
                tick()
            if idx < len(ready) - 1 and delay > 0:
                cancel.wait(delay)
    finally:
        sender.close()
        emit(("done",))
