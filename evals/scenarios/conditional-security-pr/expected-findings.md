# Expected Activation: Conditional Dependency Security PR Review

## must_activate

- `changed-files-risk-classifier` as a baseline skill.
- `dependency-security-evidence` after detecting manifest or lockfile changes.
- Full-tier security delegation when scanner evidence requires judgement.

## must_not

- Must not mark the update safe only because dependency resolution succeeds.
- Must not load database or contract analysis without matching evidence.
