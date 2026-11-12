"""
Session authentication helpers.

    - validate_new_password: run the project's AUTH_PASSWORD_VALIDATORS and
      report failures as InvalidData on the "password" field.
    - login_with_password: check credentials and start a Django session, or
      raise InvalidData with a generic message.
    - MinimumLengthValidator, UserAttributeSimilarityValidator: drop-in
      replacements of Django's password validators whose messages come from
      djkit.messages ("password_too_short", "password_too_similar"), so they
      follow DJKIT_MESSAGES. Django's own versions may come out untranslated
      (the plural form of the length message) or embed the model's field
      verbose names in the text.

Everything works with any user model (only django.contrib.auth is used).
"""

from django.contrib.auth import authenticate, login
from django.contrib.auth import password_validation
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .errors import InvalidData
from .messages import get_message


def validate_new_password(password: str, user=None, field: str = "password") -> None:
    """
    Check a new password against settings.AUTH_PASSWORD_VALIDATORS.

    Args:
        password: the plain-text password chosen by the user.
        user: the (possibly unsaved) user it belongs to, so validators such
            as UserAttributeSimilarityValidator can compare it with the
            user's data; None skips those comparisons.
        field: name of the field the errors are reported on.

    Raises:
        InvalidData: with errors={field: [messages]} when a validator fails.
    """
    try:
        validate_password(password, user)
    except ValidationError as error:
        raise InvalidData(errors={field: [str(message) for message in error.messages]}) from error


def login_with_password(request, username: str, password: str, detail: str | None = None):
    """
    Authenticate a user and start a session (sets the session cookie).

    Args:
        request: the current HttpRequest.
        username: value of the user model's USERNAME_FIELD (e.g. the email),
            already normalized by the caller.
        password: the plain-text password.
        detail: message of the error; the "login_failed" message of
            djkit.messages when omitted. Deliberately generic: it never
            reveals whether the account exists.

    Returns:
        The logged-in user.

    Raises:
        InvalidData: wrong credentials or inactive user (same message in
            both cases).
    """
    user = authenticate(request, username=username, password=password)
    if user is None:
        raise InvalidData(detail or get_message("login_failed"))
    login(request, user)
    return user


class MinimumLengthValidator(password_validation.MinimumLengthValidator):
    """
    Django's MinimumLengthValidator with the "password_too_short" message of
    djkit.messages (placeholder {min_length}).

    Use it in AUTH_PASSWORD_VALIDATORS as
    "djkit.auth.MinimumLengthValidator" (same OPTIONS as Django's).
    """

    def get_error_message(self) -> str:
        """Message of a password shorter than min_length."""
        return get_message("password_too_short", min_length=self.min_length)

    def get_help_text(self) -> str:
        """Help text describing the rule (same text as the error)."""
        return self.get_error_message()


class UserAttributeSimilarityValidator(password_validation.UserAttributeSimilarityValidator):
    """
    Django's UserAttributeSimilarityValidator with the "password_too_similar"
    message of djkit.messages, which does not name the similar field (Django
    inserts the field's verbose_name, often not in the user's language).

    Use it in AUTH_PASSWORD_VALIDATORS as
    "djkit.auth.UserAttributeSimilarityValidator" (same OPTIONS as Django's).
    """

    def validate(self, password: str, user=None) -> None:
        """
        Run Django's check and replace its message.

        Args:
            password: the plain-text password.
            user: the user whose attributes are compared (None skips the check).

        Raises:
            ValidationError: code "password_too_similar" when the password is
                too similar to one of the user's attributes.
        """
        try:
            super().validate(password, user)
        except ValidationError as error:
            raise ValidationError(get_message("password_too_similar"), code="password_too_similar") from error

    def get_help_text(self) -> str:
        """Help text describing the rule."""
        return get_message("password_too_similar")
