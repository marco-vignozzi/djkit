"""
Readable test output for `python manage.py test`.

Enabled with `TEST_RUNNER = "djkit.testing.runner.VerboseTestRunner"` in
settings. Instead of a row of dots, every test is printed on its own line,
grouped by module and class, with:

    - the outcome (PASS / FAIL / ERROR / SKIP / XFAIL / XPASS),
    - a readable name built from the method name,
    - how long it took,
    - the project source files that ran during the test (the code it
      exercises), detected automatically with `sys.monitoring`,
    - the first line of the test docstring (what the test checks), if any,
    - the reason, for skipped tests.

At the end a summary with the count of every outcome is printed, followed by
the usual unittest tracebacks for failures and errors.

Verbosity (`-v`):
    0 -> Django's default quiet output (no per-test lines).
    1 -> per-test lines (default).
    2+ -> per-test lines plus Django's own messages (test DB creation, ...).

`--debug-sql` and `--pdb` keep Django's own result classes, since they
already add their own output.

`--parallel N` works too: every worker process installs the fast test
password hashers and tracks the source files of its own tests, which reach
the main process with the other test events ("addSourceFiles"). Lines are
printed one test class at a time, as each worker finishes it. Install
`tblib` to see the tracebacks of failing tests in parallel runs (without
it, Django cannot send them from the workers).

Settings (all optional):
    DJKIT_TEST_EXCLUDED_DIRS  -> path parts never reported as code under test
                                 (default: DEFAULT_EXCLUDED_DIRS). The package
                                 of the settings module (e.g. "config" for
                                 "config.settings") is always excluded too.
    DJKIT_TEST_EXCLUDED_FILES -> file names never reported
                                 (default: DEFAULT_EXCLUDED_FILES).
    DJKIT_TEST_PASSWORD_HASHERS -> PASSWORD_HASHERS used while the tests run
                                 (default: DEFAULT_TEST_PASSWORD_HASHERS, a
                                 fast hasher); None keeps the project's own.
Files whose name starts with "test" and djkit's own testing package are
never reported either. BASE_DIR is the root of the reported paths.
"""

import sys
import unittest
from pathlib import Path

from django.conf import settings
from django.core.management.color import color_style
from django.test.runner import DiscoverRunner, ParallelTestSuite, RemoteTestResult, RemoteTestRunner, _init_worker
from django.test.utils import override_settings

# Default path parts / file names that are never reported as "code under
# test": the tests themselves, their data builders, migrations and the
# virtualenv. Overridable with DJKIT_TEST_EXCLUDED_DIRS / _FILES.
DEFAULT_EXCLUDED_DIRS = frozenset({"tests", "migrations", ".venv", "venv", "site-packages"})
DEFAULT_EXCLUDED_FILES = frozenset({"tests.py", "factories.py", "apps.py", "admin.py", "__init__.py"})

# Password hashers used while the tests run. The production hashers are slow
# on purpose (PBKDF2 with ~1M iterations, ~0.5 s per hash), and every test
# user pays that price: a fast hasher keeps the suite quick. Never used
# outside the tests. Overridable with DJKIT_TEST_PASSWORD_HASHERS.
DEFAULT_TEST_PASSWORD_HASHERS = ("django.contrib.auth.hashers.MD5PasswordHasher",)

# PASSWORD_HASHERS of the project, saved by VerboseTestRunner before it
# installs the test hashers (None while no replacement is active).
_project_password_hashers: list[str] | None = None

# This package (runner and test helpers): it runs during every test but is
# never code under test.
TESTING_PACKAGE_DIR = Path(__file__).resolve().parent

# Outcome code -> (label printed in the line, color style attribute name).
OUTCOMES = {
    "pass": ("PASS ", "SUCCESS"),
    "fail": ("FAIL ", "ERROR"),
    "error": ("ERROR", "ERROR"),
    "skip": ("SKIP ", "WARNING"),
    "xfail": ("XFAIL", "WARNING"),
    "xpass": ("XPASS", "ERROR"),
}


def excluded_dirs() -> frozenset[str]:
    """
    Path parts that are never reported as code under test.

    Returns:
        settings.DJKIT_TEST_EXCLUDED_DIRS (or DEFAULT_EXCLUDED_DIRS), plus the
        package of the settings module (e.g. "config" for "config.settings").
    """
    dirs = set(getattr(settings, "DJKIT_TEST_EXCLUDED_DIRS", DEFAULT_EXCLUDED_DIRS))
    settings_module = getattr(settings, "SETTINGS_MODULE", None) or ""
    if "." in settings_module:
        dirs.update(settings_module.split(".")[:-1])
    return frozenset(dirs)


def excluded_files() -> frozenset[str]:
    """
    File names that are never reported as code under test.

    Returns:
        settings.DJKIT_TEST_EXCLUDED_FILES, or DEFAULT_EXCLUDED_FILES.
    """
    return frozenset(getattr(settings, "DJKIT_TEST_EXCLUDED_FILES", DEFAULT_EXCLUDED_FILES))


def password_hashers_for_tests() -> list[str] | None:
    """
    Password hashers to install while the tests run.

    Returns:
        settings.DJKIT_TEST_PASSWORD_HASHERS (or DEFAULT_TEST_PASSWORD_HASHERS)
        as a list, or None when the setting is None (keep the project's own).
    """
    hashers = getattr(settings, "DJKIT_TEST_PASSWORD_HASHERS", DEFAULT_TEST_PASSWORD_HASHERS)
    return None if hashers is None else list(hashers)


def project_password_hashers() -> list[str]:
    """
    The project's real PASSWORD_HASHERS, also while the test hashers are on.

    Meant for the few tests that check how passwords are stored in
    production, e.g. `with override_settings(PASSWORD_HASHERS=project_password_hashers()):`.

    Returns:
        The hashers VerboseTestRunner replaced, or settings.PASSWORD_HASHERS
        when no replacement is active.
    """
    if _project_password_hashers is not None:
        return list(_project_password_hashers)
    return list(settings.PASSWORD_HASHERS)


def project_source(
    filename: str,
    root: Path,
    skip_dirs: frozenset[str],
    skip_files: frozenset[str],
    skip_tree: Path = TESTING_PACKAGE_DIR,
) -> str | None:
    """
    Decide whether a code file is project code under test.

    Args:
        filename: path of a Python file (`co_filename` of a code object).
        root: project root; the result is relative to it.
        skip_dirs: path parts that exclude a file (e.g. "tests").
        skip_files: file names that exclude a file (e.g. "factories.py").
        skip_tree: a directory whose files are always excluded (djkit's own
            testing package by default).

    Returns:
        The path relative to `root` in POSIX form (e.g. "shop/orders.py"),
        or None if the file is outside `root`, is not a .py file, is a test
        file ("test*.py"), is excluded, or is inside `skip_tree`.
    """
    resolved = Path(filename).resolve()
    if resolved.is_relative_to(skip_tree):
        return None
    try:
        path = resolved.relative_to(root.resolve())
    except ValueError:
        return None
    if (
        path.suffix != ".py"
        or path.name in skip_files
        or path.name.startswith("test")
        or skip_dirs.intersection(path.parts[:-1])
    ):
        return None
    return path.as_posix()


def readable_name(method_name: str) -> str:
    """
    Turn a test method name into a readable sentence.

    Args:
        method_name: e.g. "test_as_of_includes_the_day_itself".

    Returns:
        e.g. "as of includes the day itself".
    """
    if method_name.startswith("test_"):
        name = method_name.removeprefix("test_")
    else:
        name = method_name.removeprefix("test")
    return name.replace("_", " ").strip() or method_name


def first_doc_line(obj) -> str:
    """
    Return the first non-empty line of an object's docstring.

    Args:
        obj: any object (class, function...).

    Returns:
        The stripped first line, or "" when there is no docstring.
    """
    for line in (obj.__doc__ or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


class SourceTracker:
    """
    Records which project source files run while a test is executing.

    Uses `sys.monitoring` (Python 3.12+): a PY_START callback fires the first
    time each function starts, records its file if it belongs to the project
    and returns DISABLE, so every function costs one callback per test.
    `start()` re-enables the callbacks for the next test.

    Only files accepted by `project_source` are recorded (not tests,
    factories, migrations, settings package or third-party code).
    Code run in setUpClass / setUpTestData is outside any test, so it is not
    attributed to any test.
    """

    TOOL_NAME = "djkit-tests"

    def __init__(self, root: Path):
        """
        Args:
            root: project directory (BASE_DIR); reported paths are relative to it.
        """
        self.root = root.resolve()
        self.skip_dirs = excluded_dirs()
        self.skip_files = excluded_files()
        self.files: set[str] = set()
        self._relevant: dict[str, str | None] = {}  # co_filename -> rel path / None
        self.tool_id = self._claim_tool_id()
        if self.tool_id is not None:
            mon = sys.monitoring
            mon.register_callback(self.tool_id, mon.events.PY_START, self._on_start)

    def _claim_tool_id(self):
        """
        Reserve a free sys.monitoring tool id.

        Returns:
            The id, or None if monitoring is unavailable or every id is taken
            (e.g. by a coverage tool or debugger): tracking is then disabled.
        """
        mon = getattr(sys, "monitoring", None)
        if mon is None:
            return None
        for tool_id in range(6):  # ids 0-5 are available to tools
            if mon.get_tool(tool_id) is None:
                mon.use_tool_id(tool_id, self.TOOL_NAME)
                return tool_id
        return None

    def _relative_source(self, filename: str):
        """
        Decide whether a code file is project code under test.

        Args:
            filename: `co_filename` of a code object.

        Returns:
            Its path relative to `root` (e.g. "shop/orders.py"), or None.
            Results are cached per file name.
        """
        if filename not in self._relevant:
            self._relevant[filename] = project_source(filename, self.root, self.skip_dirs, self.skip_files)
        return self._relevant[filename]

    def _on_start(self, code, instruction_offset):
        """PY_START callback: record the file, then disable this location."""
        rel = self._relative_source(code.co_filename)
        if rel is not None:
            self.files.add(rel)
        return sys.monitoring.DISABLE

    def start(self):
        """Begin recording for a new test (clears the previous file set)."""
        self.files = set()
        if self.tool_id is not None:
            sys.monitoring.set_events(self.tool_id, sys.monitoring.events.PY_START)
            sys.monitoring.restart_events()

    def stop(self) -> list[str]:
        """
        Stop recording.

        Returns:
            The sorted project files that ran since `start()`.
        """
        if self.tool_id is not None:
            sys.monitoring.set_events(self.tool_id, sys.monitoring.events.NO_EVENTS)
        return sorted(self.files)

    def close(self):
        """Release the monitoring tool id."""
        if self.tool_id is not None:
            sys.monitoring.register_callback(
                self.tool_id, sys.monitoring.events.PY_START, None
            )
            sys.monitoring.free_tool_id(self.tool_id)
            self.tool_id = None


class VerboseTextTestResult(unittest.TextTestResult):
    """
    unittest result that prints one descriptive line per test.

    The outcome of the running test is stored by the add* hooks and printed
    in stopTest, when the duration is also known (unittest calls addDuration
    before stopTest). Errors raised outside a test (e.g. in setUpClass) have
    no startTest/stopTest pair and are printed immediately.
    """

    def __init__(self, stream, descriptions, verbosity, **kwargs):
        """Same arguments as unittest.TextTestResult."""
        super().__init__(stream, descriptions, verbosity, **kwargs)
        # Silence TextTestResult's own per-test output (dots / "... ok").
        self.showAll = False
        self.dots = False
        self.style = color_style()
        self._current_module = None
        self._current_class = None
        self._reset_current()
        self.counts = dict.fromkeys(OUTCOMES, 0)
        self.tracker = SourceTracker(Path(settings.BASE_DIR))
        # Source files sent by a worker process for the running test
        # (parallel runs); None when the test ran in this process.
        self._remote_files = None

    # -- helpers -----------------------------------------------------------

    def _reset_current(self):
        """Forget the state of the test that just ended."""
        self._test = None
        self._outcome = "pass"
        self._duration = None
        self._reason = ""
        self._remote_files = None

    def _set_outcome(self, test, outcome, reason=""):
        """
        Record the outcome of a test.

        Args:
            test: the test case the outcome refers to.
            outcome: a key of OUTCOMES.
            reason: optional text printed under the line (skip reason).

        A worse outcome never gets overwritten by a better one (a failed
        subtest followed by a passing test is still a failure). If `test` is
        not the running one (error in setUpClass/tearDownClass), the line is
        printed right away.
        """
        if test is not self._test:
            self.counts[outcome] += 1
            self._print_line(outcome, str(test), None, "", reason, [])
            return
        if self._outcome in ("fail", "error") and outcome == "pass":
            return
        self._outcome = outcome
        self._reason = reason

    def _print_headers(self, test):
        """Print module and class headers when they change."""
        cls = type(test)
        if cls.__module__ != self._current_module:
            self._current_module = cls.__module__
            self._current_class = None
            self.stream.writeln("")
            self.stream.writeln(self.style.MIGRATE_HEADING(cls.__module__))
        if cls is not self._current_class:
            self._current_class = cls
            doc = first_doc_line(cls)
            suffix = f" - {doc}" if doc else ""
            self.stream.writeln(f"  {self.style.HTTP_INFO(cls.__name__)}{suffix}")

    def _print_line(self, outcome, name, duration, doc, reason, files):
        """
        Print the line of one finished test.

        Args:
            outcome: a key of OUTCOMES.
            name: readable test name.
            duration: seconds, or None if unknown.
            doc: first docstring line ("" for none).
            reason: skip reason ("" for none).
            files: project source files run by the test (may be empty).
        """
        label, style_name = OUTCOMES[outcome]
        label = getattr(self.style, style_name)(label)
        timing = f" ({duration * 1000:.0f} ms)" if duration is not None else ""
        sources = f"  [{', '.join(files)}]" if files else ""
        self.stream.writeln(f"    {label} {name}{timing}{self.style.NOTICE(sources)}")
        if doc:
            self.stream.writeln(f"          {doc}")
        if reason:
            self.stream.writeln(f"          reason: {reason}")
        self.stream.flush()

    # -- unittest hooks ----------------------------------------------------

    def startTest(self, test):
        """Print headers if needed and start tracking `test`."""
        super().startTest(test)
        self._print_headers(test)
        self._reset_current()
        self._test = test
        self.tracker.start()

    def stopTest(self, test):
        """Print the line of `test` with outcome, duration and source files."""
        files = self.tracker.stop()
        if self._remote_files is not None:
            files = self._remote_files
        super().stopTest(test)
        if test is self._test:
            self.counts[self._outcome] += 1
            method = getattr(test, "_testMethodName", str(test))
            doc = first_doc_line(getattr(test, method, None)) if method else ""
            self._print_line(
                self._outcome,
                readable_name(method),
                self._duration,
                doc,
                self._reason,
                files,
            )
        self._reset_current()

    def addDuration(self, test, elapsed):
        """Store the duration of the running test."""
        super().addDuration(test, elapsed)
        if test is self._test:
            self._duration = elapsed

    def addSourceFiles(self, test, files):
        """
        Store the source files a worker process tracked for `test`
        (event sent by TrackingRemoteTestResult in parallel runs).

        Args:
            test: the test case the files belong to.
            files: project source files run by the test.
        """
        if test is self._test:
            self._remote_files = list(files)

    def addSuccess(self, test):
        """Mark the test as passed."""
        super().addSuccess(test)
        self._set_outcome(test, "pass")

    def addFailure(self, test, err):
        """Mark the test as failed (assertion error)."""
        super().addFailure(test, err)
        self._set_outcome(test, "fail")

    def addError(self, test, err):
        """Mark the test as errored (unexpected exception)."""
        super().addError(test, err)
        self._set_outcome(test, "error")

    def addSkip(self, test, reason):
        """Mark the test as skipped, keeping the reason."""
        super().addSkip(test, reason)
        self._set_outcome(test, "skip", reason)

    def addExpectedFailure(self, test, err):
        """Mark the test as an expected failure."""
        super().addExpectedFailure(test, err)
        self._set_outcome(test, "xfail")

    def addUnexpectedSuccess(self, test):
        """Mark an @expectedFailure test that passed."""
        super().addUnexpectedSuccess(test)
        self._set_outcome(test, "xpass")

    def addSubTest(self, test, subtest, err):
        """A failing subtest makes the whole test fail (or error)."""
        super().addSubTest(test, subtest, err)
        if err is not None:
            is_failure = issubclass(err[0], test.failureException)
            self._set_outcome(test, "fail" if is_failure else "error")

    def stopTestRun(self):
        """Release the source tracker at the end of the run."""
        self.tracker.close()
        super().stopTestRun()

    def printErrors(self):
        """Print the outcome summary, then the usual tracebacks."""
        self.stream.writeln("")
        parts = []
        for outcome, count in self.counts.items():
            if count:
                label, style_name = OUTCOMES[outcome]
                parts.append(getattr(self.style, style_name)(f"{count} {label.strip().lower()}"))
        self.stream.writeln("Summary: " + (", ".join(parts) or "no tests"))
        super().printErrors()


def install_test_password_hashers():
    """
    Replace PASSWORD_HASHERS with password_hashers_for_tests(), saving the
    project's own ones for project_password_hashers().

    Returns:
        The enabled override_settings (to disable it later), or None when
        DJKIT_TEST_PASSWORD_HASHERS is None (project hashers kept).
    """
    global _project_password_hashers
    hashers = password_hashers_for_tests()
    if hashers is None:
        return None
    _project_password_hashers = list(settings.PASSWORD_HASHERS)
    # override_settings also sends setting_changed, which clears Django's
    # cache of the hasher instances.
    override = override_settings(PASSWORD_HASHERS=hashers)
    override.enable()
    return override


def _init_worker_with_test_hashers(counter, *args, **kwargs):
    """
    Set up a worker process of a parallel run: Django's own setup (its test
    database, settings), then the fast test password hashers, which a
    spawned or forkserver process would not inherit from the main one. The
    override lives as long as the worker. Module-level because of the
    multiprocessing module's requirements.

    Args:
        counter, *args, **kwargs: those of django.test.runner._init_worker.
    """
    _init_worker(counter, *args, **kwargs)
    install_test_password_hashers()


class TrackingRemoteTestResult(RemoteTestResult):
    """
    Result of a worker process of a parallel run that also tracks, with
    SourceTracker, the project source files every test runs, and sends
    them to the main process as an "addSourceFiles" event before
    "stopTest" (handled by VerboseTextTestResult.addSourceFiles).
    """

    def __init__(self, *args, **kwargs):
        """Same arguments as RemoteTestResult."""
        super().__init__(*args, **kwargs)
        self.tracker = SourceTracker(Path(settings.BASE_DIR))

    def startTest(self, test):
        """Start tracking the source files of `test`."""
        super().startTest(test)
        self.tracker.start()

    def stopTest(self, test):
        """Send the tracked source files, then the usual stopTest event."""
        self.events.append(("addSourceFiles", self.test_index, self.tracker.stop()))
        super().stopTest(test)

    def stopTestRun(self):
        """Release the source tracker at the end of the subsuite."""
        self.tracker.close()
        super().stopTestRun()


class TrackingRemoteTestRunner(RemoteTestRunner):
    """RemoteTestRunner that uses TrackingRemoteTestResult."""

    resultclass = TrackingRemoteTestResult


class VerboseParallelTestSuite(ParallelTestSuite):
    """
    ParallelTestSuite whose workers install the fast test password hashers
    and track the source files of their tests.
    """

    init_worker = _init_worker_with_test_hashers
    runner_class = TrackingRemoteTestRunner


class VerboseTestRunner(DiscoverRunner):
    """
    Django test runner that uses VerboseTextTestResult.

    Falls back to Django's own result classes with `-v 0`, `--debug-sql`
    or `--pdb`. While the tests run, PASSWORD_HASHERS is replaced by
    password_hashers_for_tests() (see DEFAULT_TEST_PASSWORD_HASHERS), also
    in the worker processes of `--parallel` (VerboseParallelTestSuite).
    """

    parallel_test_suite = VerboseParallelTestSuite

    def setup_test_environment(self, **kwargs):
        """Django's test environment, plus the fast test password hashers."""
        super().setup_test_environment(**kwargs)
        self._hashers_override = install_test_password_hashers()

    def teardown_test_environment(self, **kwargs):
        """Restore the project's password hashers, then Django's teardown."""
        global _project_password_hashers
        if self._hashers_override is not None:
            self._hashers_override.disable()
            self._hashers_override = None
            _project_password_hashers = None
        super().teardown_test_environment(**kwargs)

    def get_resultclass(self):
        """Return the result class used by the unittest runner."""
        default = super().get_resultclass()
        if default is not None or self.verbosity == 0:
            return default
        return VerboseTextTestResult
