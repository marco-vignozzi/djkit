"""
Development conveniences.

    - relaxed_validation: whether the "relaxed validation" switch is on.

With DJKIT_RELAXED_VALIDATION = True (allowed only with DEBUG) the checks
that only make typing test data slow are skipped, while every rule the
program's logic depends on (uniqueness, coherence of amounts and dates,
confirmations) stays. In djkit it relaxes:

    - validate_new_password: no AUTH_PASSWORD_VALIDATORS (any password);
    - it.validate_tax_code: 1 to TAX_CODE_LENGTH letters or digits instead
      of exactly TAX_CODE_LENGTH.

djkit.testing.runner.VerboseTestRunner forces the switch off while the
tests run, so the suite always checks the production rules.

    # settings.py
    DJKIT_RELAXED_VALIDATION = env_bool("DEV_RELAXED_VALIDATION", default=False)
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def relaxed_validation() -> bool:
    """
    Whether the checks that only slow down test data entry are skipped.

    Returns:
        settings.DJKIT_RELAXED_VALIDATION (default False).

    Raises:
        ImproperlyConfigured: the switch is on while DEBUG is off (it must
            never reach production).
    """
    relaxed = bool(getattr(settings, "DJKIT_RELAXED_VALIDATION", False))
    if relaxed and not settings.DEBUG:
        raise ImproperlyConfigured("DJKIT_RELAXED_VALIDATION is allowed only with DEBUG on.")
    return relaxed
