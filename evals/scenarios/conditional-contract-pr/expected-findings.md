# Expected Activation: Conditional Contract PR Review

## must_activate

- `changed-files-risk-classifier` as a baseline skill.
- `cross-service-contract` after detecting API, event, or client contract changes.
- Full-tier contract delegation when compatibility judgement is required.

## must_not

- Must not infer backward compatibility from a successful local build alone.
- Must not load database or dependency-security analysis without matching evidence.
