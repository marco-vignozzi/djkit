"""
djkit must never depend on the project that uses it.

Every import found in the package's source files (tests included) must point
to djkit itself, Django, Django Ninja, Pydantic or the standard library, so
the folder can be extracted as a standalone package at any time.

Run with: python manage.py test djkit.tests.test_isolation
"""

import ast
import sys
from pathlib import Path

from django.test import SimpleTestCase

import djkit

# Top-level packages djkit may import besides the standard library.
ALLOWED_PACKAGES = frozenset({"djkit", "django", "ninja", "pydantic"})
PACKAGE_DIR = Path(djkit.__file__).resolve().parent


def imported_top_level_modules(source: str) -> set[str]:
    """
    List the top-level modules imported by a piece of Python source code.

    Args:
        source: content of a .py file.

    Returns:
        The first component of every absolute import ("django" for
        "from django.db import models"); relative imports are skipped,
        since they always stay inside the package.
    """
    modules = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


class PackageIsolationTests(SimpleTestCase):
    """djkit imports only itself, Django, Ninja, Pydantic and the standard library."""

    def test_helper_finds_absolute_imports_and_skips_relative_ones(self):
        """'import a.b', 'from c import d' and 'from .e import f' -> {'a', 'c'}."""
        source = "import a.b\nfrom c import d\nfrom .e import f\n"
        self.assertEqual(imported_top_level_modules(source), {"a", "c"})

    def test_no_import_outside_the_allowed_packages(self):
        """Every .py file of djkit imports only allowed packages or the standard library."""
        allowed = ALLOWED_PACKAGES | sys.stdlib_module_names
        files = sorted(PACKAGE_DIR.rglob("*.py"))
        self.assertTrue(files)
        for path in files:
            with self.subTest(file=path.relative_to(PACKAGE_DIR).as_posix()):
                foreign = imported_top_level_modules(path.read_text(encoding="utf-8")) - allowed
                self.assertEqual(foreign, set())

    def test_no_migrations_folder(self):
        """djkit has only abstract models, so it ships no migrations."""
        self.assertFalse((PACKAGE_DIR / "migrations").exists())

    def test_version_is_semantic(self):
        """__version__ has the MAJOR.MINOR.PATCH form, e.g. "0.1.0"."""
        self.assertRegex(djkit.__version__, r"^\d+\.\d+\.\d+$")
