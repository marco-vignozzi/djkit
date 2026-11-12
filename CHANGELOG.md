# Changelog

All notable changes to djkit. Versions follow semantic versioning
(MAJOR: incompatible changes, MINOR: new features, PATCH: fixes).

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

### Fixed
- `readable_name` removes only one `test_` prefix
  ("test_testing_tools" -> "testing tools", was "ing tools").
