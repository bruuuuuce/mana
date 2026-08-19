# TG07 live-pilot instructions

No live pilot was run as part of TG07. The harness is deliberately excluded
from normal CI and refuses to run unless the operator asserts both the live
flag and that provider authentication is already configured. It never asks
interactively for authentication.

## Recommended first pilot

Use Codex with the same fixed stage routes for every comparable run:

| Stage | Model | Effort |
|---|---|---:|
| Discovery | `gpt-5.6-terra` | `high` |
| Scope Triage | `gpt-5.6-sol` | `xhigh` |
| Planner | `gpt-5.6-sol` | `high` |
| Correction | `gpt-5.6-terra` | `high` |
| Trajectory checkpoint | `gpt-5.6-terra` | `high` |

Select two sanitized, reviewer-approved contexts:

1. one known story that previously showed trajectory or scope inflation; and
2. one simple control story expected to remain on track with zero checkpoints.

Run a checkpoint-only synthetic pilot first if desired. The request must meet
the TG05 synthetic-request restriction:

```bash
MANA_ANALYSIS_TRAJECTORY_LIVE_PILOT=true \
MANA_ANALYSIS_TRAJECTORY_LIVE_PILOT_CREDENTIALS_READY=true \
scripts/analysis-trajectory-live-pilot.sh \
  --project-root /path/to/project \
  --provider codex \
  --output-dir .mana/pilots/trajectory-checkpoint-control \
  --checkpoint-only /path/to/synthetic-checkpoint-request.json
```

For each approved story, run the complete off/shadow/enforce comparison into a
new project-local output directory:

```bash
MANA_ANALYSIS_TRAJECTORY_LIVE_PILOT=true \
MANA_ANALYSIS_TRAJECTORY_LIVE_PILOT_CREDENTIALS_READY=true \
MANA_CODEX_STORY_START_DISCOVERY_MODEL=gpt-5.6-terra \
MANA_CODEX_STORY_START_DISCOVERY_EFFORT=high \
MANA_CODEX_STORY_START_TRIAGE_MODEL=gpt-5.6-sol \
MANA_CODEX_STORY_START_TRIAGE_EFFORT=xhigh \
MANA_CODEX_STORY_START_PLANNER_MODEL=gpt-5.6-sol \
MANA_CODEX_STORY_START_PLANNER_EFFORT=high \
MANA_CODEX_STORY_START_CORRECTION_MODEL=gpt-5.6-terra \
MANA_CODEX_STORY_START_CORRECTION_EFFORT=high \
MANA_CODEX_STORY_START_TRAJECTORY_CHECKPOINT_MODEL=gpt-5.6-terra \
MANA_CODEX_STORY_START_TRAJECTORY_CHECKPOINT_EFFORT=high \
scripts/analysis-trajectory-live-pilot.sh \
  --project-root /path/to/project \
  --context .mana/pilot-inputs/approved-story.json \
  --provider codex \
  --output-dir .mana/pilots/trajectory-known-inflation-001
```

Repeat with the control story and another new output directory. The harness
prints all selected routes before execution, pins and checks the Git revision
and story-context hash across modes, caps each story run at four Scope v2 calls
plus at most two checkpoint calls, caps the complete A/B/C comparison at 14
provider calls and two checkpoints, and stores sanitized telemetry and route
manifests separately under `off/`, `shadow/`, and `enforce/`.

The same provider transport, route table, repository revision, story input,
and context source are used for a comparison. Remote provider sampling and
service state can still vary, so a difference is not automatically caused by
the guard. Exact usage remains `UNAVAILABLE` when the transport does not
expose trustworthy token counts.

After both story pairs, complete the TG07 human checklist. Do not infer human
acceptance from successful schemas, lower call counts, or polished prose. Keep
rollout at `SHADOW_PILOT_ONLY` until the recorded reviewer evidence supports a
different bounded state.
