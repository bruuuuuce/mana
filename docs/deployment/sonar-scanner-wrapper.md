# Sonar Scanner Wrapper

Mana can use local `sonar-scanner` output as optional evidence for branch
validation, PR readiness, and requested PR review.

Sonar is not a global Mana requirement and is not an automatic approval gate.
It produces local evidence for humans and agents to triage.

## Configuration

Keep only environment-specific and secret values in shell variables:

```bash
export SONAR_HOST_URL=http://localhost:9000
export SONAR_TOKEN=...
```

Keep project scanner properties in the project-local Mana workspace:

```text
.mana/global/sonar-project.properties
```

Initialize the file from the Mana template:

```bash
./mana sonar --init-config
```

Example properties:

```properties
sonar.projectKey=phoenix-quality-test
sonar.projectName=Phoenix Quality Test
sonar.sources=phoenix
sonar.java.binaries=phoenix/build/classes/java/main
sonar.sourceEncoding=UTF-8
sonar.scm.provider=git
sonar.exclusions=**/.git/**,**/.gradle/**,**/build/generated/**,**/build/resources/**,**/node_modules/**,**/.mana/**
```

## Commands

Validate scanner/runtime/config readiness, server reachability, and token
authentication:

```bash
./mana sonar --check
```

Print the scanner command with the token redacted:

```bash
./mana sonar --dry-run
```

Run analysis and store evidence under the active Mana workspace:

```bash
./mana sonar --analyze
```

Default output:

```text
.mana/features/<FEATURE-ID>/evidence/sonar/
  sonar-command.log
  sonar-summary.md
```

## Java Runtime

If `sonar-scanner --version` fails with an unsupported class version, select a
newer Java runtime before running Mana:

```bash
export JAVA_HOME="$HOME/.sdkman/candidates/java/21.0.11-amzn"
export PATH="$JAVA_HOME/bin:$PATH"
```

## Agent Usage

Agents should read existing `evidence/sonar/` artifacts when present. They
should not rerun Sonar unless the user requested it. Sonar findings should be
triaged against the changed branch, story, PR diff, and project policy.
