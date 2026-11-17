# Changelog

All notable changes to djkit. Versions follow semantic versioning
(MAJOR: incompatible changes, MINOR: new features, PATCH: fixes).

## [0.6.0] — unreleased

### Added (strict query)
- `api.forbid_unknown_query_params` / `StrictQueryModel`: a query parameter
  an endpoint does not declare -> 422 on that name (`unknown_query_param`);
  enabled by `DJKIT_FORBID_UNKNOWN_QUERY_PARAMS` (`DjkitConfig.ready`).

### Added (pagination)
- `pagination`: `PageNumber` (Django Ninja paginator, `?page=&size=`,
  answer `{items, count, page, size, pages}`), `page_of`, `Page`,
  `page_sizes`, `default_page_size`; settings `DJKIT_PAGE_SIZES`,
  `DJKIT_PAGE_SIZE`; message keys `page_size_not_allowed`,
  `page_out_of_range`; an unordered QuerySet raises `ValueError`.

### Changed
- `api.validation_message`: an empty text where one character is required
  (`string_too_short`, `min_length` 1) gets the `missing` message instead
  of "Enter at least 1 characters.".

### Added
- `workspaces`: separate workspaces in one database (multi-tenancy):
  abstract `WorkspaceModel` and `MembershipModel` (role, one admin per
  workspace, one membership per user), the active workspace
  (`memberships`, `active_membership`, `active_workspace`,
  `is_workspace_admin`, `switch_workspace`, `acting_in`, `forget_active`),
  setting `DJKIT_WORKSPACE_ADMIN_ROLE`, message key `workspace_not_found`;
  `leave`; invitations: abstract `InvitationModel` (token stored only as
  its SHA-256), `new_invitation_token`, `token_digest`,
  `find_open_invitation`, setting `DJKIT_INVITATION_VALID_DAYS`, message
  key `invitation_not_found`.
- `retention`: dates of the purge of deleted rows and of the warning
  before it (`DJKIT_RETENTION_DAYS`, `DJKIT_RETENTION_WARNING_DAYS`).
- `dev.relaxed_validation` (`DJKIT_RELAXED_VALIDATION`, development only):
  `auth.validate_new_password` accepts any password, `it.validate_tax_code`
  1 to 16 characters; the test runner forces it off
  (`install_strict_validation`).
- `it.TaxCodeValidator` replaces the `RegexValidator` of `validate_tax_code`
  (same rules; projects need an `AlterField` migration).
- `views.spa_index`: catch-all serving the SPA `index.html` (`DJKIT_SPA_INDEX`).
- `mail`: blocked domains (`DJKIT_MAIL_BLOCKED_DOMAINS`, default
  `RESERVED_DOMAINS` of RFC 2606 / 6761; `blocked_domains`, `is_blocked`):
  `send_email` never writes to them and returns `False` when no recipient
  is left. **Behaviour change:** emails to `example.com` & co. are no
  longer sent by default.
- `clients`: `client_address(request, proxy_count)` and `client_key`
  (keyed hash of the address) for the abuse limits of public endpoints.
- `audit.rate_limit_until(entries, limit, window_seconds)`: at most N
  actions in a time window, counted on the log.
- `numbers.round_half_up(value, step=CENT)`: halves away from zero.
- `it.format_date`, `format_amount`, `format_percent`, `format_names`:
  Italian formats of the values put inside texts.
- `notices`: deadline notices (`NoticeRule`, `rules`, `deadline_key`,
  `to_notify`, `sent_for`, `record`, `prune`, `MAX_DAYS_BEFORE`) and the
  abstract models `NoticePreferenceBase` and `DeadlineNoticeBase`.
- `access`: one access policy (`AccessPolicy`, setting `DJKIT_ACCESS_POLICY`)
  with `Action` (`READ`, `WRITE`), `AccessLevel` (`FULL`, `READ_ONLY`),
  `get_policy`, `scope`, `level`, `check`; `get_accessible_or_404` takes
  `action` and `read_only_detail` and goes through the policy (a row
  readable but not writable -> `Forbidden`).
- `errors.Forbidden` (403, message key `read_only`), registered in
  `api.DEFAULT_STATUS_CODES`.
- `testing.runner`: `--parallel N` works with `VerboseTestRunner`. The
  worker processes install the fast test password hashers too
  (`VerboseParallelTestSuite`, `install_test_password_hashers`) and send
  the source files of each test to the main process
  (`TrackingRemoteTestResult`, event `addSourceFiles`).
- `db.ensure_unique` accepts a QuerySet instead of the model class, to
  check uniqueness inside a subset of rows (e.g. a partial unique
  constraint).
- `numbers.split_by_weights(total, weights, step)`: proportional parts
  that add up exactly to the total (largest remainder method).
- `numbers.minimal_transfers(balances)`: the fewest transfers that bring
  balances adding up to zero to zero.

- `audit.AuditAction.NOTIFY`: a message sent about a row (e.g. an email
  reminder); `log_write` stores `{}` when no changes are given. Projects
  with a concrete entry model need a migration (choices and constraint).
- `audit.last_logged_at(entries, object_ids)`: newest entry of each object
  among already filtered entries, in one query.
- `audit.ActorKind` (`USER`, `BATCH`) and the field
  `AuditEntryBase.actor_kind` (default `USER`), with the checks
  `<app>_<class>_actor_kind_valid` and `<app>_<class>_batch_without_actor`
  (`AuditEntryBase.actor_kind_constraints(prefix)` for subclasses that
  redefine `Meta.constraints`); `log_write(..., actor_kind=...)` refuses a
  BATCH entry with an actor. Projects need a migration.
- `audit.cooldown_seconds`, `cooldown_until`, `ensure_cooldown`: optional
  short anti-spam block between two sends about the same object, based on
  the audit log (no table of its own); setting `DJKIT_COOLDOWN_SECONDS`
  (default 60).
- `errors.TooManyRequests(retry_at)` -> 429 with `retry_at`;
  `api.ErrorOut.retry_at`.

### Changed
- `testing.api.ApiTestCase.assertNotAccessible` fails when the path
  matches no route (or only the catch-all `views.page_not_found`): a
  removed URL answered 404 too and made the test pass without checking.

### Documentation
- `views.page_not_found` as the catch-all route after the API: a JSON 404
  for unknown API paths with DEBUG on too.

## [0.5.0] — unreleased

### Added
- `deadlines.urgency(due_date, today, levels, overdue)`: code of a deadline
  by how close it is (e.g. overdue / this week / this month).

### Changed
- `db.date_filter` also accepts an expression or `OuterRef` as `as_of`, for
  a reference date that changes from row to row.

## [0.4.0] — unreleased

### Added
- `deadlines` (new module): `Deadline` and `DeadlineRegistry` (one
  provider per kind of deadline, `collect(user, start, end, kinds)` merges
  and checks them), for calendars and notifications.
- `dates.yearly_anniversaries(origin, start, end)`: anniversaries of a date
  in a period (29 February -> 28 February in common years).

## [0.3.0] — unreleased

### Added
- `texts` (new module): `TextCatalog` (nested texts with dotted keys,
  plural leaves, loud errors on unknown keys or missing placeholders),
  `catalog_response` (JSON with ETag / 304), `typescript_keys`; command
  `export_text_types`; settings `DJKIT_TEXT_CATALOG`,
  `DJKIT_TEXT_PUBLIC_SECTIONS`.
- `messages`: key `tax_code_invalid`.
- `errors`: `InvalidData.from_validation_error(error, field_prefix="")`
  names the fields of an object nested in the request body
  ("customer.email"); helper `prefixed_field`.
- `validators.strip_text_values`: removes the spaces around the text
  values of a request before model validation.
- `mail` (new module): `render_email` (subject and body from two
  templates), `send_email` (plain-text email through `django.core.mail`,
  errors raised to the caller), `demo_mode`, `ReadableConsoleBackend` (development backend printing
  emails as readable text); setting `DJKIT_MAIL_DEMO_MODE`
  (emails only logged). Replaces the planned `send_email(subject, body, to,
  demo_mode=...)` and `DJKIT_DEMO_MODE`.
- `api.InputSchema`: base of request bodies that rejects undeclared fields
  (Pydantic `extra_forbidden` -> 422 with message key `unknown_field`);
  `ConfirmationIn` now inherits it.
- `numbers` (new module): `split_evenly` (equal parts with a fixed
  precision, leftover steps to the first parts).
- `audit`: setting `DJKIT_AUDIT_MASKED_FIELDS`, `mask_changes`,
  `mask_value`, `masked_fields`; `log_write` masks those fields (message
  key `audit_masked`).
- `auth`: password reset by link, `password_reset_token`,
  `user_for_password_reset`, `reset_password` (message key
  `password_reset_invalid`).

### Changed
- `it.validate_tax_code`: its message comes from the key
  `tax_code_invalid` (it was an Italian sentence written in djkit).

### Fixed
- `api.validation_message`: a list that is too short or too long (Pydantic
  `too_short` / `too_long`) now uses the new message keys `list_too_short`
  and `list_too_long` ("Enter at least 1 items."), not the string ones
  ("Enter at least 1 characters.").
- `updates.apply_patch`: a value equal to the stored one but written
  differently (`Decimal("650")` for a stored 650.00) no longer appears in
  the returned diff; the diff lists only the fields really saved.

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
