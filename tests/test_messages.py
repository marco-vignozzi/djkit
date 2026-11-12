"""
Tests for djkit.messages (user-facing messages looked up by key).

Run with: python manage.py test djkit.tests.test_messages
"""

from django.test import SimpleTestCase, override_settings

from djkit.messages import DEFAULT_MESSAGES, get_message, missing_messages


class GetMessageTests(SimpleTestCase):
    """get_message returns the project's text or the English default."""

    @override_settings(DJKIT_MESSAGES={})
    def test_default_text_without_setting(self):
        """No project texts -> 'not_found' is 'Not found.'."""
        self.assertEqual(get_message("not_found"), "Not found.")

    @override_settings(DJKIT_MESSAGES={"not_found": "Introuvable."})
    def test_project_text_replaces_default(self):
        """DJKIT_MESSAGES {'not_found': 'Introuvable.'} -> 'Introuvable.'; other keys keep the default."""
        self.assertEqual(get_message("not_found"), "Introuvable.")
        self.assertEqual(get_message("conflict"), DEFAULT_MESSAGES["conflict"])

    @override_settings(DJKIT_MESSAGES={"string_too_short": "Au moins {min_length} caractères."})
    def test_placeholders_are_filled(self):
        """'Au moins {min_length} caractères.' with min_length=3 -> 'Au moins 3 caractères.'."""
        self.assertEqual(get_message("string_too_short", min_length=3), "Au moins 3 caractères.")

    @override_settings(DJKIT_MESSAGES={})
    def test_missing_placeholder_value_leaves_text_unformatted(self):
        """'string_too_short' without min_length -> the bare text, no error."""
        self.assertEqual(get_message("string_too_short"), DEFAULT_MESSAGES["string_too_short"])

    @override_settings(DJKIT_MESSAGES={"custom": "Testo del progetto."})
    def test_project_defined_key(self):
        """A key present only in DJKIT_MESSAGES -> its text."""
        self.assertEqual(get_message("custom"), "Testo del progetto.")

    def test_unknown_key_raises_key_error(self):
        """'no_such_key' -> KeyError (a typo is caught, not shown to the user)."""
        with self.assertRaises(KeyError):
            get_message("no_such_key")


class MissingMessagesTests(SimpleTestCase):
    """missing_messages lists the default keys the project has not given."""

    @override_settings(DJKIT_MESSAGES={"not_found": "Introuvable."})
    def test_lists_every_key_but_the_given_ones(self):
        """Only 'not_found' given -> every other default key, sorted."""
        expected = sorted(key for key in DEFAULT_MESSAGES if key != "not_found")
        self.assertEqual(missing_messages(), expected)

    @override_settings(DJKIT_MESSAGES={})
    def test_all_missing_without_setting(self):
        """No project texts -> every default key."""
        self.assertEqual(missing_messages(), sorted(DEFAULT_MESSAGES))
