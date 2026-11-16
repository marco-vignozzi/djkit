"""
Email sending.

    - render_email: build subject and body of an email from two Django
      templates ("<name>_subject.txt" and "<name>_body.txt"), so the texts
      (and their language) live in the project, not in the code.
    - send_email: send one plain-text email with django.core.mail, or only
      write it to the log in demo mode (DJKIT_MAIL_DEMO_MODE) or when every
      recipient is in a blocked domain (DJKIT_MAIL_BLOCKED_DOMAINS).
    - blocked_domains / is_blocked: the domains never written to (by
      default the reserved ones of RFC 2606 and RFC 6761, used by sample
      and test data).
    - ReadableConsoleBackend: development email backend that prints emails
      in the terminal as plain text (Django's console backend prints the
      encoded message: accented text turns into quoted-printable, where
      links get "=3D" and broken lines, impossible to copy).

Which server is used (console in development, SMTP in production, memory
in the tests) is decided by Django's EMAIL_BACKEND setting. Errors are never
swallowed: a failing server raises to the caller, which decides what the
user sees.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


# Domains reserved for examples and tests (RFC 2606, RFC 6761): no real
# mailbox lives there. A domain also covers its subdomains.
RESERVED_DOMAINS = ("example.com", "example.net", "example.org", "example", "invalid", "test", "localhost")


def blocked_domains() -> tuple[str, ...]:
    """
    The domains emails are never sent to.

    Returns:
        settings.DJKIT_MAIL_BLOCKED_DOMAINS (lowercase), RESERVED_DOMAINS
        when missing; () turns the check off.
    """
    return tuple(domain.lower().strip(".") for domain in getattr(settings, "DJKIT_MAIL_BLOCKED_DOMAINS", RESERVED_DOMAINS))


def is_blocked(address: str) -> bool:
    """
    Whether an address is in a blocked domain (or a subdomain of one).

    Args:
        address: an email address.

    Returns:
        True for e.g. "anna@example.com" or "x@mail.test" with the default
        domains.
    """
    domain = address.rsplit("@", 1)[-1].lower().strip(".")
    return any(domain == blocked or domain.endswith("." + blocked) for blocked in blocked_domains())


def demo_mode() -> bool:
    """
    Whether emails are only logged instead of being sent.

    Returns:
        settings.DJKIT_MAIL_DEMO_MODE, False when missing.
    """
    return bool(getattr(settings, "DJKIT_MAIL_DEMO_MODE", False))


def render_email(template_name: str, context: dict) -> tuple[str, str]:
    """
    Render subject and body of an email from templates.

    Args:
        template_name: path without suffix, e.g. "shop/emails/welcome":
            the templates "<template_name>_subject.txt" and
            "<template_name>_body.txt" must exist.
        context: values available to both templates.

    Returns:
        (subject, body): the subject on one line (newlines and surrounding
        spaces removed, since headers cannot contain them), the body as
        rendered.
    """
    subject = render_to_string(f"{template_name}_subject.txt", context)
    body = render_to_string(f"{template_name}_body.txt", context)
    return " ".join(subject.split()), body


def send_email(
    to: list[str],
    subject: str,
    body: str,
    *,
    reply_to: list[str] | None = None,
    from_email: str | None = None,
) -> bool:
    """
    Send one plain-text email.

    Args:
        to: recipient addresses.
        subject: subject line.
        body: plain-text body.
        reply_to: optional Reply-To addresses (e.g. the user on whose
            behalf a shared sender writes).
        from_email: sender; settings.DEFAULT_FROM_EMAIL when None.

    Returns:
        True when the email was handed to the email backend (to the
        recipients not blocked, see is_blocked); False in demo mode or when
        every recipient is blocked (the email is only logged, with its
        recipients and subject).

    Raises:
        Any error of the email backend (e.g. smtplib.SMTPException): the
        email is never dropped silently.
    """
    if demo_mode():
        logger.info("Demo mode, email not sent: to=%s subject=%r", to, subject)
        return False
    blocked = [address for address in to if is_blocked(address)]
    if blocked:
        logger.info("Blocked domain, email not sent to %s: subject=%r", blocked, subject)
    to = [address for address in to if not is_blocked(address)]
    if not to:
        return False
    message = EmailMessage(subject=subject, body=body, from_email=from_email, to=to, reply_to=reply_to)
    message.send(fail_silently=False)
    return True


class ReadableConsoleBackend(ConsoleEmailBackend):
    """
    Email backend for development: prints every email in the terminal as
    readable text (headers that matter, then the body exactly as written).

    Use it as EMAIL_BACKEND = "djkit.mail.ReadableConsoleBackend". Same
    options as Django's console backend (e.g. stream).
    """

    def write_message(self, message) -> None:
        """
        Write one email to the stream.

        Args:
            message: the EmailMessage being sent.
        """
        headers = [
            ("From", message.from_email),
            ("To", ", ".join(message.to)),
            ("Cc", ", ".join(message.cc)),
            ("Reply-To", ", ".join(message.reply_to)),
            ("Subject", message.subject),
        ]
        lines = [f"{name}: {value}" for name, value in headers if value]
        self.stream.write("\n".join(lines) + "\n\n" + message.body + "\n")
        self.stream.write("-" * 79 + "\n")
