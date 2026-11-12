"""Django application configuration of the djkit framework."""

from django.apps import AppConfig


class DjkitConfig(AppConfig):
    """
    Registers djkit as a Django app, so its tests are discovered by
    `manage.py test djkit`. djkit has no concrete models and no migrations.
    """

    name = "djkit"
    verbose_name = "djkit"
