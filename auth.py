"""
Session authentication helpers.

    - validate_new_password: run the project's AUTH_PASSWORD_VALIDATORS and
      report failures as InvalidData on the "password" field.
    - login_with_password: check credentials and start a Django session, or
      raise InvalidData with a generic message.
    - password_reset_token / user_for_password_reset / reset_password:
      "forgot / change password" through a link sent by email, with
      Django's default_token_generator (valid PASSWORD_RESET_TIMEOUT
      seconds, and only until the password changes: a link works once).
    - MinimumLengthValidator, UserAttributeSimilarityValidator: drop-in
      replacements of Django's password validators whose messages come from
      djkit.messages ("password_too_short", "password_too_similar"), so they
      follow DJKIT_MESSAGES. Django's own versions may come out untranslated
      (the plural form of the length message) or embed the model's field
      verbose names in the text.

Everything works with any user model (only django.contrib.auth is used).
"""

from django.contrib.auth import authenticate, get_user_model, login
from django.contrib.auth import password_validation
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

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


def password_reset_token(user) -> tuple[str, str]:
    """
    Credentials of a password reset link for a user.

    Args:
        user: the (saved) user who asked to reset the password.

    Returns:
        (uid, token): the user's primary key encoded in URL-safe base64 and
        a token of default_token_generator. The token depends on the
        password hash, the last login and the email, so it stops working
        when the password changes (one use only) or after
        PASSWORD_RESET_TIMEOUT seconds.
    """
    return urlsafe_base64_encode(force_bytes(user.pk)), default_token_generator.make_token(user)


def user_for_password_reset(uid: str, token: str, detail: str | None = None):
    """
    Find the user of a password reset link and check its token.

    Args:
        uid: the encoded primary key (first value of password_reset_token).
        token: the token (second value).
        detail: message of the error; the "password_reset_invalid" message
            when omitted.

    Returns:
        The user, active and with a valid token.

    Raises:
        InvalidData: malformed uid, unknown or inactive user, wrong, expired
            or already used token (same message in every case).
    """
    user_model = get_user_model()
    try:
        pk = urlsafe_base64_decode(uid).decode()
        user = user_model._default_manager.get(pk=pk)
    except (TypeError, ValueError, OverflowError, ValidationError, user_model.DoesNotExist):
        user = None
    if user is None or not user.is_active or not default_token_generator.check_token(user, token):
        raise InvalidData(detail or get_message("password_reset_invalid"))
    return user


def reset_password(uid: str, token: str, new_password: str, field: str = "new_password", detail: str | None = None):
    """
    Set a new password from a password reset link.

    The password hash changes, so the link stops working and every session
    of the user opened before is no longer valid (Django checks the session
    hash on each request).

    Args:
        uid, token: the credentials of the link (see password_reset_token).
        new_password: the plain-text password chosen by the user.
        field: name of the field the password errors are reported on.
        detail: message of the invalid-link error (see
            user_for_password_reset).

    Returns:
        The user, saved with the new password.

    Raises:
        InvalidData: invalid link (no "errors"), or password rejected by
            AUTH_PASSWORD_VALIDATORS (errors={field: [...]}).
    """
    user = user_for_password_reset(uid, token, detail)
    validate_new_password(new_password, user, field)
    user.set_password(new_password)
    user.save(update_fields=["password"])
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
