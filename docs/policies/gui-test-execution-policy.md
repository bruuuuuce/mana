# GUI Test Execution Policy

## Purpose
Allow repeatable browser validation while preventing a low-cost agent from
becoming an exploratory operator of live systems or sensitive test data.

## Required Catalog Contract
Each GUI entry must declare `kind: gui`, an approved Playwright command,
`environment`, `execution_status`, `safety`, timeout, source references,
redacted test-data references, and `approved: true`. The catalog target must
declare `classification: isolated_test`; production and unknown targets are
always refused. The catalog also declares an absolute local `project_root`;
the Playwright config is resolved only relative to that root.

The referenced Playwright config must enable `trace`, `screenshot`, and
`video`. The runner adds a JUnit reporter and stores all artifacts under the
declared Mana workspace run directory.

## Execution Gates
1. An agent selects a catalog ID only. It cannot provide a command, URL, or
   credentials at execution time.
2. `scripts/run-gui-testbook.sh` requires a matching environment, approved and
   runnable state, isolated target, and `requires_explicit_gui_approval`.
3. The command must be a local `playwright test` invocation from the approved
   catalog. It may not invoke a shell chain, remote URL, CI command, or another
   package script.
4. Secret values are supplied outside Mana. The catalog stores references only;
   logs and summaries must redact secret values and sensitive URLs.
5. Test data must be test-only, resettable, and isolated. Real payment
   instruments, customer data, production systems, and irreversible writes are
   prohibited.

## Evidence And Verdicts
Preserve `run-report.yaml`, JUnit XML, Playwright output, traces, screenshots,
and video in the local Mana workspace with access appropriate for test
credentials and data. Browser artifacts are not automatically redacted and
must not be published, attached to tickets, or placed in prompts without a
separate review. `failed` means the runner failed; it is not a regression claim.
Use `inconclusive` when evidence cannot distinguish product, selector, data,
dependency, or environment cause. Proposed testbook learning always requires
owner approval.
