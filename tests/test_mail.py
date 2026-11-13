"""
Tests for djkit.mail.

Django's test runner replaces the email backend with the in-memory one, so
sent emails land in django.core.mail.outbox. Templates come from a
locmem loader defined here, independent of the project.

Run with: python manage.py test djkit.tests.test_mail
"""

from io import StringIO

from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.test import SimpleTestCase, override_settings

from djkit.mail import ReadableConsoleBackend, render_email, send_email

# Templates of render_email, served from memory.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "OPTIONS": {
            "loaders": [
                (
                    "django.template.loaders.locmem.Loader",
                    {
                        "greet_subject.txt": "Hello\n  {{ name }}  \n",
                        "greet_body.txt": "{% autoescape off %}Dear {{ name }}, see {{ link }}{% endautoescape %}",
                    },
                )
            ]
        },
    }
]


class FailingBackend(BaseEmailBackend):
    """Email backend that always fails, like an unreachable SMTP server."""

    def send_messages(self, email_messages):
        """Raise instead of sending."""
        raise ConnectionError("SMTP server unreachable")


@override_settings(TEMPLATES=TEMPLATES)
class RenderEmailTests(SimpleTestCase):
    """render_email builds subject and body from two templates."""

    def test_subject_on_one_line_and_body_rendered(self):
        """Subject 'Hello\\n  Anna' -> 'Hello Anna'; body with the context values, '&' not escaped."""
        subject, body = render_email("greet", {"name": "Anna", "link": "https://x.test/?a=1&b=2"})
        self.assertEqual(subject, "Hello Anna")
        self.assertEqual(body, "Dear Anna, see https://x.test/?a=1&b=2")


class SendEmailTests(SimpleTestCase):
    """send_email sends a plain-text email, or only logs it in demo mode."""

    def test_sends_with_default_sender_and_reply_to(self):
        """True; one email in the outbox with recipients, subject, body, DEFAULT_FROM_EMAIL and Reply-To."""
        with override_settings(DEFAULT_FROM_EMAIL="noreply@example.com"):
            sent = send_email(["anna@example.com"], "Subject", "Body", reply_to=["owner@example.com"])
        self.assertTrue(sent)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual((message.to, message.subject, message.body), (["anna@example.com"], "Subject", "Body"))
        self.assertEqual((message.from_email, message.reply_to), ("noreply@example.com", ["owner@example.com"]))

    @override_settings(DJKIT_MAIL_DEMO_MODE=True)
    def test_demo_mode_only_logs(self):
        """DJKIT_MAIL_DEMO_MODE=True -> False, nothing in the outbox, recipients and subject in the log."""
        with self.assertLogs("djkit.mail", level="INFO") as logs:
            sent = send_email(["anna@example.com"], "Subject", "Body")
        self.assertFalse(sent)
        self.assertEqual(mail.outbox, [])
        self.assertIn("anna@example.com", logs.output[0])

    @override_settings(EMAIL_BACKEND="djkit.tests.test_mail.FailingBackend")
    def test_backend_errors_reach_the_caller(self):
        """A failing server -> its exception is raised, never swallowed."""
        with self.assertRaises(ConnectionError):
            send_email(["anna@example.com"], "Subject", "Body")


class ReadableConsoleBackendTests(SimpleTestCase):
    """ReadableConsoleBackend prints emails as plain text, links copyable."""

    def test_body_printed_as_written(self):
        """Accented body with a link 'a=1&b=2' -> printed as is (no '=3D', no broken lines), with To and Subject."""
        stream = StringIO()
        message = mail.EmailMessage(
            "Oggetto", "Si può usare: https://x.test/?uid=MQ&token=" + "a" * 80, to=["anna@example.com"]
        )
        ReadableConsoleBackend(stream=stream).send_messages([message])
        output = stream.getvalue()
        self.assertIn("To: anna@example.com\nSubject: Oggetto\n", output)
        self.assertIn("Si può usare: https://x.test/?uid=MQ&token=" + "a" * 80 + "\n", output)
        self.assertNotIn("=3D", output)
