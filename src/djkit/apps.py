"""Django application configuration of the djkit framework."""

from django.apps import AppConfig


class DjkitConfig(AppConfig):
    """
    Registers djkit as a Django app, so its tests are discovered by
    `manage.py test djkit`. djkit has no concrete models and no migrations.
    """

    name = "djkit"
    verbose_name = "djkit"

    def ready(self) -> None:
        """
        With DJKIT_FORBID_UNKNOWN_QUERY_PARAMS = True, reject the query
        parameters an endpoint does not declare (djkit.api), before any
        API module declares its endpoints.
        """
        from django.conf import settings

        if getattr(settings, "DJKIT_FORBID_UNKNOWN_QUERY_PARAMS", False):
            from .api import forbid_unknown_query_params

            forbid_unknown_query_params()
