# Sample Output

## Scenario: developer in chat asks to switch to pre-mortem before pushing

**User input:** "I'm about to push — I want to run the pre-mortem first."

**Output:**

```yaml
skill: profile-selector
status: ready
selected_profile: jessica-fletcher
profile_switch_command: "scripts/run-profile.sh jessica-fletcher --project-root ."
active_profile_written: ".mana/active-profile"
previous_active_profile: null
summary: "Active profile set to jessica-fletcher (production pre-mortem before commit or push)."
warnings: []
human_review_required: false
```

**Console message:**

```
Active profile switched to: jessica-fletcher
Run: scripts/run-profile.sh jessica-fletcher --project-root .

jessica-fletcher asks: why would this branch fail in production?
Expected duration: ~5 minutes.
No human approval required to run; blocker findings require owner decision.
```

---

## Scenario: overwrite warning

**User input:** "switch to pr-ready"

**Current `.mana/active-profile`:** `jessica-fletcher`

**Output:**

```yaml
skill: profile-selector
status: needs_human_decision
selected_profile: pr-ready
profile_switch_command: "scripts/run-profile.sh pr-ready --project-root ."
active_profile_written: null
previous_active_profile: jessica-fletcher
summary: "jessica-fletcher is the current active profile. Confirm switch to pr-ready?"
warnings:
  - "Active profile jessica-fletcher will be replaced. Confirm to proceed."
human_review_required: true
```
