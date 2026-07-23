# Scenario: Conditional Contract PR Review

**Profile:** `pr-ready`
**Activation signal:** `api_event_or_client_contract_change`
**Expected skill:** `cross-service-contract`

## Setup

1. In a scratch branch, add `inputs/changes.txt` to the filtered diff inventory.
2. Run `pr-ready` with a full-tier specialist available.

## Intent

The API and event schema changes activate contract analysis. The runner must
look for compatibility and test evidence instead of treating generated clients
or schemas as ordinary source changes.
