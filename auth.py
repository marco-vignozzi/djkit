"""
Session authentication helpers.

    - validate_new_password: run the project's AUTH_PASSWORD_VALIDATORS and
      report failures as InvalidData on the "password" field.
    - login_with_password: check credentials and start a Django session, or
      raise InvalidData with a generic message.

Both work with any user model (they rely only on django.contrib.auth).
"""

from django.contrib.auth import authenticate, login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .errors import InvalidData

# Message of a failed login. Deliberately generic: it never reveals whether
# the account exists or only the password is wrong.
DEFAULT_LOGIN_FAILED_DETAIL = "Invalid credentials."


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
        detail: message of the error; DEFAULT_LOGIN_FAILED_DETAIL when omitted.

    Returns:
        The logged-in user.

    Raises:
        InvalidData: wrong credentials or inactive user (same message in
            both cases).
    """
    user = authenticate(request, username=username, password=password)
    if user is None:
        raise InvalidData(detail or DEFAULT_LOGIN_FAILED_DETAIL)
    login(request, user)
    return user
