# Mana Workspace Templates

These templates define the project-local `.mana/` workspace used by agents and skills. They are copied or rendered by `scripts/mana-workspace.sh` when a project starts a feature or canonical-branch session.

Every workspace includes `agent-memory/story-trace.md`, the canonical story-specific trace for concise reasoning summaries, assumptions, decisions, approval gates, handoffs, and links to generated artifacts.

Every workspace also includes `decisions/developer-choice-log.md`, the canonical log of implementation choices discussed with and confirmed by developers.

The shared Service Context Layer includes `.mana/global/knowledge/`: a compact
index plus stable and candidate evidence-backed service knowledge cards. It is
not a raw analysis or chat-history store.
