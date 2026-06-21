# Sample Output

```yaml
skill: developer-decision-review
status: warning
questions:
  - severity: warning
    area: integration
    question: "Why was this call kept synchronous instead of following the async integration pattern?"
    evidence: "ContractService.updateContract"
    required_before_pr: true
outputs:
  - developer_decision_review
  - decision_questions
  - unexplained_choices
human_review_required: true
```

