# Scenario: Insufficient evidence

**Profile:** `bug-hunt`
**Exercises:** evidence classification.

## Intent

The named code exposes a suspicious retry branch but no caller, configuration,
or test establishes the failure precondition. The workflow must label the gap
as insufficient evidence or hypothesis, with a suggested reproducer, rather
than assert a confirmed defect.
