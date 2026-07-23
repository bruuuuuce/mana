# Testbook Execution Policy

## Purpose
Allow low-cost agents to discover, run, and report local tests without giving
them authority to invent commands or operate unsafe environments.

## Catalog States
- `discovered_not_runnable`: evidence exists, but no verified command or
  prerequisites are available.
- `needs_environment`: a command may be known, but services, data, credentials,
  or a declared target are still required.
- `runnable`: the command has repository evidence and may be considered for
  approval. It is still not executable until `approved: true`.

## Execution Gates
1. The agent may select only a `test_id` from the catalog.
2. `scripts/run-testbook.sh` reads the command from that entry and refuses
   unapproved entries, incompatible environments, and performance tests without
   explicit allowance.
3. Test execution is local or on a declared dedicated test environment. Never
   run against production.
4. Every entry declares `timeout_seconds`; the runner enforces it.
5. Do not infer or print credentials, secrets, customer data, or target URLs.
6. Preserve command output and result metadata under the Mana workspace.

## Model Routing
Discovery, test selection, and report formatting are `economy` work. A stronger
model or human owner is required for root-cause claims, performance-baseline
acceptance, cross-service production risk, and contradictory evidence.

## Verdicts
- `passed`: command completed successfully and expected artifacts are present
  when declared.
- `failed`: command returned a non-zero exit code.
- `blocked`: approval, tool, environment, or policy gate prevented execution.
- `partial`: only a requested subset completed.
- `inconclusive`: logs or artifacts cannot distinguish regression from setup,
  dependency, data, or environment failure.
