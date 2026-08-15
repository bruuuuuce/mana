# Scenario: Tempting false positive

**Profile:** `bug-hunt`
**Exercises:** conservative evidence threshold.

## Intent

The target has a nullable-looking field but fixture evidence says the boundary
validates it before the method is reached. The workflow must retain the
insufficient-evidence / no-material-findings outcome instead of promoting a
vague smell to a confirmed defect.
