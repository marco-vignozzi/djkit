# Changelog

All notable changes to djkit. Versions follow semantic versioning
(MAJOR: incompatible changes, MINOR: new features, PATCH: fixes).

## [0.2.0] — unreleased

### Added
- `auth` (new module): `validate_new_password` (password validators ->
  `InvalidData` on a field), `login_with_password` (authenticate + login,
  generic `InvalidData` on failure), `DEFAULT_LOGIN_FAILED_DETAIL`.
- `db`: `ensure_unique` (values already used by other rows -> `Conflict`
  with per-field errors), `DEFAULT_UNIQUE_MESSAGE`.
- `api`: `csrf_protected` and `sets_csrf_cookie` operation decorators for
  public (`auth=None`) endpoints of a session-based API.
- `messages` (new module): every user-facing message has a key and an
  English default (`DEFAULT_MESSAGES`); projects give their own texts with
  the `DJKIT_MESSAGES` setting. `get_message`, `missing_messages`,
  `configured_messages`.
- `views` (new module): JSON error views `csrf_failure` (for
  `CSRF_FAILURE_VIEW`), `bad_request`, `permission_denied`,
  `page_not_found`, `server_error` (for `handler400`...`handler500`).
- `api.register_error_handlers` also converts Django Ninja's own errors:
  schema `ValidationError` -> 422 `ErrorOut` with per-field messages
  (`validation_errors`, `error_field`, `validation_message`), `HttpError`
  (401, 403 CSRF, 400 unparsable body, 429, ...) and `Http404`, all with
  `messages` texts (`http_error_message`).
- `auth`: `MinimumLengthValidator` and `UserAttributeSimilarityValidator`,
  Django's password validators with `messages` texts.
- `db`: logical deletion. `SoftDeleteModel` (abstract, `is_deleted` and
  `deleted_at` fields, `deleted_state_constraint`, `mark_deleted`),
  `SoftDeleteQuerySet` (`alive`, `deleted`, `filter_deleted`,
  `mark_deleted`; `accessible_by(user, include_deleted=False)` hides
  deleted rows), `DeletedFilter` (`exclude` / `include` / `only`) and
  `ensure_not_deleted` (409 on a write to a deleted row, message key
  `deleted_read_only`).
- `db.AccessibleQuerySet`: optional `ACCESS_CONDITIONS` on the model, extra
  lookups applied in the same `filter()` as `ACCESS_PATH`.
- `access.get_accessible_or_404`: `include_deleted` argument.
- `testing.runner`: `VerboseTestRunner` uses fast password hashers while
  the tests run (`DEFAULT_TEST_PASSWORD_HASHERS`, setting
  `DJKIT_TEST_PASSWORD_HASHERS`, `None` to keep the project's own);
  `password_hashers_for_tests`, `project_password_hashers` for the tests
  that check the real hashers.

### Changed
- `errors`: the default detail of each exception comes from its
  `message_key` (djkit.messages) instead of the `default_detail` class
  attribute, which is removed.
- `db.ensure_unique`, `updates.apply_patch` and `auth.login_with_password`
  take their default texts from `messages`; the constants
  `DEFAULT_UNIQUE_MESSAGE` and `DEFAULT_LOGIN_FAILED_DETAIL` are removed.

## [0.1.0] — unreleased

### Added
- `dates`: `clamped_date`, `add_months`, `monthly_due_dates`.
- `db`: `AccessibleQuerySet` (`ACCESS_PATH`, `accessible_by`, `_model`),
  `sum_subquery` (precision configurable with `max_digits` / `decimal_places`),
  `count_subquery`, `date_filter`.
- `validators`: `normalize_email_address`.
- `it`: `TAX_CODE_LENGTH`, `validate_tax_code`, `normalize_tax_code`.
- `testing.runner`: `VerboseTestRunner`, `project_source`, `excluded_dirs`,
  `excluded_files`, `readable_name`, `first_doc_line`; settings
  `DJKIT_TEST_EXCLUDED_DIRS` and `DJKIT_TEST_EXCLUDED_FILES`; the settings
  package and `djkit.testing` are always excluded from the reported files.

- `errors`: `DomainError` (`detail`, `extra`, `payload()`), `NotFound`,
  `Conflict`, `InvalidData` (+ `from_validation_error`), `ConfirmationRequired`,
  `require_confirmation`.
- `api`: `register_error_handlers` (custom status codes, Django
  `ValidationError` -> 422), `ErrorOut`, `ConfirmationIn`.
- `audit`: `AuditAction`, abstract `AuditEntryBase` (+ `action_constraint`;
  `actor` reverse accessor `<app>_<class>_entries`, unique per subclass),
  `log_write`, `snapshot`, `diff`, `to_json_value`; setting
  `DJKIT_AUDIT_EXCLUDED_FIELDS`.
- `updates`: `apply_patch`.
- `access`: `get_accessible_or_404`.
- `fields`: `choice_field`, `choices_constraint`, `money_field`,
  `positive_constraint`.
- `testing.api`: `ApiClient`, `make_user`, `ApiTestCase`.

### Fixed
- `readable_name` removes only one `test_` prefix
  ("test_testing_tools" -> "testing tools", was "ing tools").
