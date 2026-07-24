# Testing Policy

## Always Protect
- `{{critical_behavior_or_legacy_flow}}`

## Green Border Expectations
- Unit tests: `{{unit_expectation}}`
- Integration tests: `{{integration_expectation}}`
- Contract tests: `{{contract_expectation}}`
- Regression tests: `{{regression_expectation}}`

## Test Data Rules
- `{{test_data_rule}}`

## Flaky Test Handling
- `{{flaky_policy}}`

## Testbook
- Catalog location: `{{testbook_location}}`
- Approval owner for executable entries: `{{testbook_approval_owner}}`
- Allowed test environments: `{{testbook_allowed_environments}}`
- Performance target and baseline policy: `{{performance_test_policy}}`

## GUI Testbook
- Isolated GUI test environments: `{{gui_test_allowed_environments}}`
- GUI target classification rule: `{{gui_target_classification_rule}}`
- Secret and test-data reference policy: `{{gui_secret_reference_policy}}`
- Required Playwright evidence: `{{gui_playwright_artifact_policy}}`

## API And Database Validation
- API test runner and isolated target policy: `{{api_test_runner_policy}}`
- Database read-verification and DBA approval policy: `{{database_read_verification_policy}}`
