# Mana Artifact Taxonomy

## Scope and Status

This taxonomy records the repository-owned producers that currently write under
a linked project's `.mana/` tree. It describes present storage, not a required
migration or a UI hierarchy. The future inspect read model owns the logical
classification; producers retain ownership of their existing persistence
contracts.

Paths are project-relative patterns. A pattern with `<workspace>` resolves only
to an existing `.mana/features/<id>` or `.mana/sessions/<id>` workspace.

## Classification Terms

- **canonical**: authoritative producer state or delivery evidence.
- **derived**: deterministic projection or report that can be rebuilt from its
  declared inputs.
- **alias/latest**: a convenience copy of a canonical revision, never a second
  revision.
- **cache**: rebuildable state whose loss does not invalidate canonical data.
- **ephemeral**: local operational state, lock, staging, or bootstrap support;
  it is not delivery evidence.

All artifact contents, path names, model-produced metadata, user input, and
external-tool output are untrusted. A read model must report safely recognized
metadata only after validation; it must never execute, follow an unsafe path, or
treat prose as an authoritative relation.

## Logical Families

| Family | Producers | Current path patterns and format | Identity, status, and time | Relations and source anchors | Class | Sensitivity / redaction |
|---|---|---|---|---|---|---|
| Project bootstrap and linkage | `bootstrap-project.sh` | `.mana/env`, `.mana/README.md`, `.mana/links/**`, `.mana/jira-mcp.env` | No product artifact ID; linkage is keyed by path. | Links point to framework resources; `env` identifies framework/project paths. | ephemeral | Environment/configuration may reveal local paths; Jira env is secret-bearing and must be excluded from public detail. |
| Service context | `mana-workspace.sh`, Sonar initializer | `.mana/global/{service-mission,architecture,engineering-guards,domain-glossary,integration-map,testing-policy,database-policy}.md`, rules/knowledge/hooks config, Sonar config | No intrinsic IDs; path identity. Timestamps are filesystem observations only. | Workspace/profile outputs may reference these files. | canonical | May contain internal architecture or operational policy; render as owner-controlled text, never parse prose into relations. |
| User Context mirror | `mana context refresh` via `mana-context.sh` / user-context library | `.mana/user-context/**`, `.mana/user-context-state` | Managed entry provenance is external; mirror paths are local. | Derived from the host-owned User Context source, not project Service Context. | derived / ephemeral state | Personal guidance; advisory, read-only, and potentially private. Exclude raw state and never elevate to project truth. |
| Workspace and identity | `mana-workspace.sh` | `.mana/features/<feature>/manifest.yaml`, `.mana/sessions/<session>/manifest.yaml`, `index.md`, `.mana/active-workspace`, `.mana/active-profile` | `workspace_id`, feature ID or session ID; manifest carries branch, purpose, created_at, and canonical-branch status. | A workspace is parent of its routed artifacts; active files are aliases, not ownership changes. | canonical; active files are alias/latest | Branch and feature identifiers can be sensitive project metadata. |
| Goal, profile, agent, and skill outputs | profile runners, agents, skills, `run-profile.sh` | `<workspace>/{context,planning,agent-memory,skill-outputs,decisions,tests,validation,pr,learning}/**` | Usually no intrinsic ID; path identity unless an embedded schema declares one. Status/timestamps are format-specific. | Story trace, developer choice log, decision log, requirement/evidence references when explicitly recorded. | canonical unless a producer labels a report derived | May include Jira, PR, source, customer, or decision data. Index metadata only by default; do not scrape arbitrary Markdown claims. |
| Evidence and source anchors | Jira Docker wrapper, dependency evidence, Sonar wrapper, evidence-index, profile outputs | `<workspace>/evidence/{jira,sonar,dependencies,verification,repair,repair-loop}/**`, `evidence/index.md` | IDs and run identity depend on subtype. Index generation timestamp is derived. | Explicit source path, URI, issue/PR identifiers, digests, and verification references when a subtype contract supplies them. | Canonical subtype evidence; `index.md` is derived | Jira payloads, scanner logs, dependency reports, and raw tool output can be sensitive. Surface references/digests/status before contents. |
| Validation, review, readiness, and decisions | agents/skills and workspace templates | `<workspace>/validation/**`, `pr/**`, `decisions/**`, `tests/**` | Path identity; specific formats can declare run/story/PR IDs and statuses. | Explicit links to requirements, evidence, source maps, and approvals only. | canonical | Human decisions and review findings require owner visibility; never infer approval from a filename or report prose. |
| Verification | `mana-verify.sh`, verification library | `<workspace>/evidence/verification/<run-id>/{result.json,result.sha256,summary.md,*.log}` | `runId`, `runtimeExecutionId`, project revision, generated/started timestamps; per-check fingerprints. | Schema v1/v2 result references skill/spec/check, bounded output artifacts, target/action/execution fingerprints, and runtime event identity. | canonical result and sidecar; summary/logs are supporting derived/raw evidence | Logs are bounded but can contain source/tool output. Preserve references and redaction boundaries; do not execute stored rerun descriptors. |
| Bounded repair | `mana-repair.sh`, `mana-repair-loop.sh` | `<workspace>/evidence/repair/<attempt-id>/…`, `evidence/repair-loop/<loop-id>/…`, temporary locks/staging below `.mana/` | `attemptId`, `loopId`, runtime execution ID, target and digest identities; result schemas define status/times. | Repair records reference immutable verification evidence and target/attempt results; they do not embed trusted patch semantics. | canonical attempt/loop result; locks/staging are ephemeral | Candidate patches, prompts, raw logs, and temporary paths are restricted. Never expose secrets, full diffs, or staging paths as catalog detail. |
| Runtime audit | cast/runtime-event library and `mana-verify.sh` | `.mana/runtime/events/<execution-id>.jsonl`, `.mana/runtime/sessions/<execution-id>.json` | `execution-id`; append order and envelope timestamp; session snapshot. | Events may reference profile/component IDs and delivery evidence. Runtime is not delivery evidence. | canonical operational audit | Explicitly excludes prompts, reasoning, credentials, tokens, source contents, and arbitrary payloads. Keep compact attributes and redact defensively. |
| Project-local learning candidates | `mana-learning.sh` | `.mana/learning/candidates/<candidate-id>.json` | Candidate ID, status, recurrence/staleness and event references; lifecycle is constrained. | Derived from selected runtime events; review artifacts may be linked explicitly. | canonical local candidate | Candidates are observations, not truth; reject secret/personal-bearing strings and do not imply cross-project promotion. |
| Cross-project User Learning | `mana-user-learning.sh` | No canonical project write for signals/clusters/candidates/reviews: external state. Project-local mirror only appears through User Context refresh. | Schema IDs for signals, clusters, candidates and reviews; external lifecycle/status. | Explicit source decision/log and provenance IDs. | excluded from project catalog except mirror metadata | External state is outside the selected project and must not be scanned. |
| Journey graph | `mana-journey.sh`, `mana-scout.sh` | `.mana/learning/journeys/<jrn>/journey.yaml`, `records/<id>-<type>.yaml` (JSON syntax), `derived/**`, `assets/**` | Mana-owned immutable `jrn_`, `jn_`, `je_`, `anc_`, `ev_`, `exp_`, `enr_`, `hyp_`, `occ_`, `trv_`, `cyc_`, `git_`, `tle_`, `hya_`, `dia_` IDs; Journey metadata includes repository revision. | Strict schema and cross-record references; source anchors identify repository-relative path/range/revision. `materialize` emits `mana.learning.graph/v1`. | Metadata/records canonical; `derived/**` cache; assets derived | Source paths/ranges and evidence summaries can expose code structure. Consumers use producer materialization, never parse records independently. |
| Concepts and teaching | `mana-concepts.sh` | `.mana/learning/unresolved-concepts/ucp_*.yaml`; Journey `ConceptOccurrence` records | Canonical registry owns `cpt_*`; unresolved candidate has host ID; occurrence has immutable Journey record ID. | Occurrences reference selected Journey node, bounded evidence, and classifier request; labels is a consumer projection. | unresolved candidates canonical local proposals; labels/projections derived | Classifier output cannot mint IDs or topology. Unresolved labels may be unreviewed/model-produced. |
| Explanations, rationale, history, and diagrams | `mana-expand.sh`, `mana-rationale.sh`, `mana-history.sh`, `mana-diagram.sh` | `.mana/learning/{expansion-requests,rationale-requests}/**`; Journey explanation/hypothesis/history/diagram records; `journeys/<jrn>/derived/expansions/**`, `assets/*.puml` | Request IDs and immutable Journey record IDs; enrichment lifecycle status. | All semantic relations are schema-validated Journey references to existing nodes, evidence, anchors, hypotheses, and diagrams. | Journey records canonical; requests/context/assets derived or ephemeral as documented | Bounded source and Git history data can be sensitive. Hypotheses are not established intent; PlantUML is derived. |
| Scout and cycle diagnostics | `mana-scout.sh` | `.mana/learning/scout-requests/**`, `journeys/<jrn>/derived/{scout-report,cycle-report}.json`, Journey records | Request ID/path and Journey record IDs; report stop reason/status. | Scout creates anchored Journey records; hardening references existing nodes/edges only. | Journey records canonical; requests/reports derived or ephemeral | Static discovery is deliberately narrow. Diagnostic labels are not runtime proof. |
| Evaluations and governance | `mana-eval.sh`, `mana-governance-report.sh` | `.mana/evaluations/results/<scenario>/<project-revision>/<run-id>.json`, `latest.json`; `.mana/reports/governance/<project-revision>/<run-id>.md`, `latest.md` | Scenario ID, project revision, run ID, generated time, schema version. | Governance report reads evaluation and learning inventory; `latest` aliases the immutable run. | canonical revision; `latest` alias/latest | Structural results do not prove semantic quality, production safety, or human approval. |
| Tool discovery and generated support | `discover-testbook.sh`, dependency/Sonar wrappers, repair/user-context temporary helpers | `.mana/testbook.discovered.yaml`, workspace testbooks, dependency/Sonar outputs, dot-prefixed lock/staging/previous files | Usually path identity; explicit test/catalog IDs only where their own contract provides them. | May support verification or a profile; relation must be declared by the consuming contract. | derived, cache, or ephemeral | Treat generated commands, logs, locks, and backups as unsafe/untrusted until their owning contract validates them. |
| Unknown and legacy | Any existing workspace content not matched above | Any regular project-relative path below `.mana/` not recognized by v1 | `artifact_id` is path-based; revision is content-derived. Status/timestamp are unavailable unless safely known. | Parent-directory and workspace containment are the only relations; no prose inference. | unknown | Default to conservative metadata. Do not expose ignored secrets, traverse symlinks, or mutate/rewrite old workspaces. |

## Inventory Completeness and Deliberate Exclusions

The producer trace covers all repository scripts that currently write or
materialize under `.mana/`: bootstrap, workspace, profiles/cast/runtime,
evidence indexing, Jira/dependency/Sonar support, verification, repair,
learning, Journey and Knowledge enrichments, evaluation, governance, testbook
discovery, and User Context materialization.

Read-only consumers are not producers: `mana-runtime.sh`, `mana-explore.sh`,
and the read portion of `mana-doctor.sh`. The external User Learning store is
also excluded because it is deliberately outside the selected project root.
Temporary lock/staging/backup paths are classified as ephemeral when discovered
rather than omitted; an inspect implementation must not make them canonical.

## Cross-Family Relations

The catalog may expose only these relation forms in v1:

1. **containment** from validated project-relative path and workspace/Journey
   layout;
2. **declared references** from a validated schema or structured contract, such
   as a verification result's run ID or a Journey record's referenced IDs;
3. **source anchors** already present in a validated producer contract; and
4. **alias-of** for explicit `latest` files and active-workspace/profile
   pointers.

Markdown links, filenames, source-text matches, and model-generated prose are
not authoritative relations. They may remain artifact content, but cannot add
a relation without a later declared contract.

## Compatibility Notes

Existing workspaces remain readable without manifests, complete schemas, or
new registration files. A missing, malformed, unreadable, unsupported, or
legacy artifact is catalogued as `unknown` with a safe diagnostic, not
silently discarded or rewritten. Existing `evidence/index.md` and
`mana runtime` retain their current commands and outputs; a later inspect
command may reuse their validated inputs but must publish a separate versioned
contract.
