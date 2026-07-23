# Scenario: Conditional Dependency Security PR Review

**Profile:** `pr-ready`
**Activation signal:** `dependency_manifest_or_lockfile_change`
**Expected skill:** `dependency-security-evidence`

## Setup

1. In a scratch branch, add `inputs/changes.txt` to the filtered diff inventory.
2. Provide existing scanner evidence showing the updated dependency has a
   high-severity advisory.
3. Run `pr-ready` with a full-tier specialist available.

## Intent

The manifest and lockfile changes activate dependency-security evidence. The
runner must preserve the advisory and owner follow-up rather than summarize the
dependency update as routine maintenance.
