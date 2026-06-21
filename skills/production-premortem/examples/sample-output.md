# Sample Output

```yaml
skill: production-premortem
status: warning
summary: "The branch has three plausible production risk paths."
likely_failure_modes:
  - severity: warning
    hypothesis: "Timeout fallback can hide failed downstream authorization."
    evidence:
      - "New catch block returns default success-like status."
    production_symptom: "Orders progress while authorization is incomplete."
    recommended_action: "Return explicit pending state and add integration test."
production_blast_radius:
  affected_flows:
    - "payment authorization"
  affected_data:
    - "payment status"
missing_detection_signals:
  - "No metric for downstream timeout fallback."
mitigation_checklist:
  - "Add timeout integration test."
  - "Add alertable metric."
human_review_required: true
```
