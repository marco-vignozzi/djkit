"""
manage.py export_text_types: write the TypeScript keys of the text catalog.

    python manage.py export_text_types --output ../frontend/src/texts/keys.ts

Reads the catalog of DJKIT_TEXT_CATALOG and exports the sections of
DJKIT_TEXT_PUBLIC_SECTIONS (djkit.texts.typescript_keys). Without --output
the module is printed.
"""

from pathlib import Path

from django.core.management.base import BaseCommand

from djkit.texts import project_catalog, typescript_keys


class Command(BaseCommand):
    """Write (or print) the TypeScript module with the text keys."""

    help = "Export the keys of the text catalog as a TypeScript type."

    def add_arguments(self, parser) -> None:
        """--output: file to write; omitted -> print to stdout."""
        parser.add_argument("--output", help="TypeScript file to write (printed when omitted)")

    def handle(self, *args, output=None, **options) -> None:
        """Generate the module and write or print it."""
        source = typescript_keys(project_catalog())
        if output is None:
            self.stdout.write(source, ending="")
            return
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        self.stdout.write(f"Text keys written to {path}")
