"""
Unit tests for djkit.testing.runner (the pure helpers; the runner itself is
exercised by every test run).

Run with: python manage.py test djkit.tests.test_runner
"""

import io
import unittest
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from djkit.testing import runner
from djkit.testing.runner import (
    DEFAULT_EXCLUDED_DIRS,
    DEFAULT_EXCLUDED_FILES,
    DEFAULT_TEST_PASSWORD_HASHERS,
    TESTING_PACKAGE_DIR,
    excluded_dirs,
    excluded_files,
    first_doc_line,
    password_hashers_for_tests,
    project_password_hashers,
    project_source,
    readable_name,
)

ROOT = Path("/srv/project")


def source(relative: str) -> str | None:
    """
    Run project_source on a file under ROOT with the default exclusions
    (plus "config" as settings package).

    Args:
        relative: path relative to ROOT, e.g. "shop/orders.py".

    Returns:
        What project_source returns.
    """
    return project_source(str(ROOT / relative), ROOT, DEFAULT_EXCLUDED_DIRS | {"config"}, DEFAULT_EXCLUDED_FILES)


class ReadableNameTests(SimpleTestCase):
    """Test method names become sentences; docstrings give their first line."""

    def test_prefix_removed_and_underscores_become_spaces(self):
        """'test_as_of_includes_the_day' -> 'as of includes the day'."""
        self.assertEqual(readable_name("test_as_of_includes_the_day"), "as of includes the day")

    def test_only_one_test_prefix_removed(self):
        """'test_testing_tools' -> 'testing tools' (not 'ing tools')."""
        self.assertEqual(readable_name("test_testing_tools"), "testing tools")

    def test_first_doc_line_skips_blank_lines(self):
        """A docstring starting with a newline -> its first non-empty line."""

        def documented():
            """
            First line.
            Second line.
            """

        self.assertEqual(first_doc_line(documented), "First line.")
        self.assertEqual(first_doc_line(lambda: None), "")


class ProjectSourceTests(SimpleTestCase):
    """project_source reports only project code under test."""

    def test_application_file_reported_relative_to_root(self):
        """/srv/project/shop/orders.py -> 'shop/orders.py'."""
        self.assertEqual(source("shop/orders.py"), "shop/orders.py")

    def test_tests_factories_migrations_and_settings_excluded(self):
        """Test files, factories, migrations, the settings package and non-.py files are skipped."""
        for relative in (
            "shop/tests/test_orders.py",
            "shop/tests.py",
            "shop/test_helpers.py",
            "shop/factories.py",
            "shop/migrations/0001_initial.py",
            "config/settings.py",
            "shop/templates/page.html",
        ):
            with self.subTest(file=relative):
                self.assertIsNone(source(relative))

    def test_file_outside_root_excluded(self):
        """A third-party file outside the project root -> None."""
        self.assertIsNone(project_source("/usr/lib/python3/json/decoder.py", ROOT, frozenset(), frozenset()))

    def test_testing_package_always_excluded(self):
        """djkit's runner is never reported, even when it lies under the root."""
        runner = TESTING_PACKAGE_DIR / "runner.py"
        self.assertIsNone(project_source(str(runner), TESTING_PACKAGE_DIR.parent.parent, frozenset(), frozenset()))


class ExclusionSettingsTests(SimpleTestCase):
    """Exclusions come from DJKIT_TEST_EXCLUDED_* settings, with defaults."""

    @override_settings(SETTINGS_MODULE="mysite.conf.settings")
    def test_default_dirs_plus_settings_package(self):
        """Without the setting: defaults + 'mysite' and 'conf' from SETTINGS_MODULE."""
        self.assertEqual(excluded_dirs(), DEFAULT_EXCLUDED_DIRS | {"mysite", "conf"})

    @override_settings(DJKIT_TEST_EXCLUDED_DIRS={"fixtures"}, SETTINGS_MODULE="config.settings")
    def test_custom_dirs_replace_defaults(self):
        """DJKIT_TEST_EXCLUDED_DIRS={'fixtures'} -> {'fixtures', 'config'}."""
        self.assertEqual(excluded_dirs(), {"fixtures", "config"})

    @override_settings(DJKIT_TEST_EXCLUDED_FILES={"conftest.py"})
    def test_custom_files_replace_defaults(self):
        """DJKIT_TEST_EXCLUDED_FILES={'conftest.py'} -> {'conftest.py'}."""
        self.assertEqual(excluded_files(), {"conftest.py"})


class PasswordHashersForTestsTests(SimpleTestCase):
    """The runner swaps in fast password hashers; the project's stay reachable."""

    def test_default_is_the_fast_hasher(self):
        """Without the setting -> DEFAULT_TEST_PASSWORD_HASHERS (MD5PasswordHasher)."""
        self.assertEqual(password_hashers_for_tests(), list(DEFAULT_TEST_PASSWORD_HASHERS))

    @override_settings(DJKIT_TEST_PASSWORD_HASHERS=None)
    def test_none_keeps_the_project_hashers(self):
        """DJKIT_TEST_PASSWORD_HASHERS=None -> None (no replacement)."""
        self.assertIsNone(password_hashers_for_tests())

    def test_runner_installed_the_test_hashers_and_kept_the_project_ones(self):
        """During the run PASSWORD_HASHERS is the test list; project_password_hashers() gives the saved one."""
        hashers = password_hashers_for_tests()
        if hashers is None:
            self.skipTest("DJKIT_TEST_PASSWORD_HASHERS is None in this project.")
        self.assertEqual(settings.PASSWORD_HASHERS, hashers)
        self.assertIsNotNone(runner._project_password_hashers)
        self.assertEqual(project_password_hashers(), runner._project_password_hashers)


class ParallelRunTests(SimpleTestCase):
    """--parallel: workers set up the test hashers and send the source files of each test."""

    def test_parallel_suite_uses_the_tracking_workers(self):
        """VerboseTestRunner.parallel_test_suite -> workers with the test hashers and TrackingRemoteTestRunner."""
        suite = runner.VerboseTestRunner.parallel_test_suite
        self.assertIs(suite, runner.VerboseParallelTestSuite)
        self.assertIs(suite.init_worker, runner._init_worker_with_test_hashers)
        self.assertIs(suite.runner_class.resultclass, runner.TrackingRemoteTestResult)

    def test_source_files_event_comes_before_stop_test(self):
        """A worker result records ("addSourceFiles", index, files) just before ("stopTest", index)."""
        result = runner.TrackingRemoteTestResult()
        result.startTest(self)
        result.addSuccess(self)
        result.stopTest(self)
        result.stopTestRun()
        names = [event[0] for event in result.events]
        self.assertEqual(names[-3:], ["addSourceFiles", "stopTest", "stopTestRun"])
        self.assertIsInstance(result.events[-3][2], list)

    def test_main_result_prints_the_files_sent_by_the_worker(self):
        """VerboseTextTestResult: addSourceFiles(["shop/orders.py"]) -> the line lists that file."""
        stream = unittest.runner._WritelnDecorator(io.StringIO())
        result = runner.VerboseTextTestResult(stream, descriptions=True, verbosity=1)
        result.startTest(self)
        result.addSourceFiles(self, ["shop/orders.py"])
        result.addSuccess(self)
        result.stopTest(self)
        result.stopTestRun()
        self.assertIn("shop/orders.py", stream.getvalue())
