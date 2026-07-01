---
name: sonar-configuration-guide
version: 1.0.0
description: Guides users through configuring Mana's local Sonar scanner properties under .mana/global/sonar-project.properties, validating SONAR_HOST_URL and SONAR_TOKEN, checking project paths such as sources and Java binaries, and preparing reusable Sonar evidence for branch validation or PR review.
compatibility:
  - codex
  - junie
  - claude
preferred_runner: codex
allowed_tools:
  - read_files
  - code_search
  - git_read
  - shell_command
inputs:
  - project_root
  - sonar_host_url
  - sonar_token_presence
  - sonar_project_properties
  - build_layout
outputs:
  - sonar_configuration_report
  - sonar_project_properties_patch
  - sonar_readiness_check
risk_level: low
owner_role: Developer / Team Leader
tags:
  - sonar
  - quality
  - configuration
  - review-evidence
---

# Sonar Configuration Guide

## Purpose
Help a user configure local Sonar scanner support for a project without putting
secrets or environment-specific values in project properties.

This skill configures evidence collection. It does not decide PR approval,
merge readiness, or release readiness by itself.

## When To Use It
- The user wants to run `sonar-scanner` through Mana.
- `.mana/global/sonar-project.properties` is missing or likely wrong.
- `SONAR_HOST_URL` or `SONAR_TOKEN` is missing.
- `sonar.java.binaries`, `sonar.sources`, or exclusions need to be adapted to
  the repository layout.
- Branch validation or requested PR review needs Sonar evidence.

## When Not To Use It
- Do not use it to hide scanner findings.
- Do not put `SONAR_TOKEN` into `.mana/global/sonar-project.properties`.
- Do not edit source code to satisfy Sonar unless a human explicitly asks for
  implementation changes.
- Do not treat Sonar output as an automatic merge gate unless project policy
  explicitly defines that gate.

## Inputs
- project_root
- sonar_host_url
- sonar_token_presence
- sonar_project_properties
- build_layout

## Outputs
- sonar_configuration_report
- sonar_project_properties_patch
- sonar_readiness_check

## Execution Logic
1. Check whether `sonar-scanner` exists and whether `sonar-scanner --version`
   runs. If it fails, report Java/runtime mismatch before editing config.
2. Check only these environment variables:
   - `SONAR_HOST_URL`
   - `SONAR_TOKEN`
3. Check for `.mana/global/sonar-project.properties`. If missing, recommend:
   `./mana sonar --init-config`.
4. Inspect repository layout before proposing properties:
   - project key and name from repository/service name when no stronger signal
     exists;
   - `sonar.sources` from the real source root;
   - `sonar.java.binaries` from the build output that exists after a build;
   - exclusions for VCS, Gradle/Maven/build outputs, generated sources,
     resources, node modules, and Mana artifacts.
5. Ask for missing project identity only when it cannot be inferred safely.
6. Run or recommend `./mana sonar --check` after configuration. The check must
   verify scanner runtime, `SONAR_HOST_URL`, `SONAR_TOKEN`, local properties,
   Sonar server reachability, and token authentication without printing the
   token.
7. If the check passes and the user wants evidence, run or recommend
   `./mana sonar --analyze`.

## Recommended Properties
Use this shape in `.mana/global/sonar-project.properties`:

```properties
sonar.projectKey=<project-quality-key>
sonar.projectName=<Project Quality Name>
sonar.sources=<source-root>
sonar.java.binaries=<compiled-classes-path>
sonar.sourceEncoding=UTF-8
sonar.scm.provider=git
sonar.exclusions=**/.git/**,**/.gradle/**,**/build/generated/**,**/build/resources/**,**/node_modules/**,**/.mana/**
```

For multi-module repositories, prefer comma-separated explicit source roots
over scanning the repository root.

## Decision Rules
- `blocker`: `sonar-scanner` cannot run, config file missing for analysis,
  `SONAR_HOST_URL` missing, `SONAR_TOKEN` missing, or required source paths are
  clearly wrong.
- `warning`: Java binaries are missing because the project has not been built,
  project key/name are placeholders, or exclusions are too broad/narrow.
- `info`: optional refinements such as project naming, extra exclusions, or
  follow-up with team policy.

## Artifact Policy
Sonar execution writes evidence under the active Mana workspace:

```text
.mana/features/<FEATURE-ID>/evidence/sonar/
  sonar-command.log
  sonar-summary.md
```

Agents may read these artifacts during `branch-ready`, `requested-pr-review`,
`pr-ready`, or `jessica-fletcher`. They should use Sonar as supporting evidence,
not as the sole decision source.

## Human Approval
Developer or Team Leader owns the local configuration. Security or platform
owners own server URL/token policy. Reviewers own PR decisions.

## Output Standard
Follow `docs/standards/agent-skill-output-standard.md` (Agent And Skill Output
Standard). Use `templates/standard-agent-skill-report.template.md` when no more
specific template exists.

Internal reasoning must use compact caveman mode: terse fragments,
evidence-first notes, no long narrative, and no private chain-of-thought in
final artifacts. Maintain a context budget: keep a short working summary with
objective, project root, config path, env presence, scanner status, checked
paths, open questions, and next checks.

## Example Output
```yaml
skill: sonar-configuration-guide
status: warning
summary: "Sonar config exists, but sonar.java.binaries is missing until the Gradle build runs."
findings:
  - severity: warning
    area: "scanner-runtime"
    message: "sonar-scanner is installed but Java runtime is too old for this scanner version."
    recommended_action: "Use Java 11+ or align scanner installation before running ./mana sonar --analyze."
outputs:
  - sonar_configuration_report
  - sonar_readiness_check
human_review_required: false
```
