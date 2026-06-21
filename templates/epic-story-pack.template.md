# Epic Story Pack

Use this file when Jira MCP is unavailable, incomplete, or intentionally not
used. Treat it as a read-only Jira fallback input for planning and validation.

## Source Metadata

- Source mode: `manual-md-fallback`
- Jira unavailable reason: `{{missing_credentials / wrong_project / offline / policy_denied / other}}`
- Captured by: `{{name_or_role}}`
- Captured at: `{{iso_datetime}}`
- Source links or screenshots: `{{links_or_paths}}`
- Confidence: `{{high / medium / low}}`

## Epic

- Epic key: `{{EPIC-123}}`
- Title: `{{epic_title}}`
- Status: `{{status}}`
- Owner: `{{owner}}`
- Business goal: `{{business_goal}}`
- Non-goals: `{{non_goals}}`
- Success metrics: `{{success_metrics}}`
- Target release or milestone: `{{release_or_milestone}}`

### Epic Description

`{{epic_description}}`

### Epic Acceptance Criteria

- `{{epic_acceptance_criterion_1}}`
- `{{epic_acceptance_criterion_2}}`

### Epic Constraints

- Architecture: `{{architecture_constraints}}`
- Security or compliance: `{{security_constraints}}`
- Database or migration: `{{database_constraints}}`
- Integration or API contracts: `{{integration_constraints}}`
- Operational constraints: `{{operational_constraints}}`

## Stories

### Story 1

- Story key: `{{STORY-1}}`
- Title: `{{story_title}}`
- Status: `{{status}}`
- Owner: `{{owner}}`
- Parent epic: `{{EPIC-123}}`
- Priority: `{{priority}}`
- Estimate: `{{estimate}}`
- Dependencies: `{{dependencies}}`

#### User Story

As a `{{actor}}`, I want `{{capability}}`, so that `{{outcome}}`.

#### Description

`{{story_description}}`

#### Acceptance Criteria

- Given `{{context}}`, when `{{action}}`, then `{{expected_result}}`.
- Given `{{context}}`, when `{{action}}`, then `{{expected_result}}`.

#### Technical Notes

- Impacted components: `{{components}}`
- APIs/events/messages: `{{contracts}}`
- Database changes: `{{db_changes}}`
- Feature flags/config: `{{flags_or_config}}`
- Observability: `{{logs_metrics_traces}}`

#### Test Notes

- Unit tests: `{{unit_test_notes}}`
- Integration tests: `{{integration_test_notes}}`
- Contract tests: `{{contract_test_notes}}`
- Regression tests: `{{regression_test_notes}}`

#### Open Questions

- `{{question}}` - Owner: `{{owner_role}}`

### Story 2

- Story key: `{{STORY-2}}`
- Title: `{{story_title}}`
- Status: `{{status}}`
- Owner: `{{owner}}`
- Parent epic: `{{EPIC-123}}`
- Priority: `{{priority}}`
- Estimate: `{{estimate}}`
- Dependencies: `{{dependencies}}`

#### User Story

As a `{{actor}}`, I want `{{capability}}`, so that `{{outcome}}`.

#### Description

`{{story_description}}`

#### Acceptance Criteria

- Given `{{context}}`, when `{{action}}`, then `{{expected_result}}`.
- Given `{{context}}`, when `{{action}}`, then `{{expected_result}}`.

#### Technical Notes

- Impacted components: `{{components}}`
- APIs/events/messages: `{{contracts}}`
- Database changes: `{{db_changes}}`
- Feature flags/config: `{{flags_or_config}}`
- Observability: `{{logs_metrics_traces}}`

#### Test Notes

- Unit tests: `{{unit_test_notes}}`
- Integration tests: `{{integration_test_notes}}`
- Contract tests: `{{contract_test_notes}}`
- Regression tests: `{{regression_test_notes}}`

#### Open Questions

- `{{question}}` - Owner: `{{owner_role}}`

## Cross-Story Consistency

- Shared assumptions: `{{shared_assumptions}}`
- Ordering constraints: `{{ordering_constraints}}`
- Contract compatibility: `{{contract_compatibility}}`
- Regression areas: `{{regression_areas}}`
- Risks if only one story ships: `{{partial_delivery_risks}}`

## Evidence Gaps

- `{{missing_jira_field_or_link}}` - Impact: `{{impact}}` - Owner: `{{owner_role}}`
