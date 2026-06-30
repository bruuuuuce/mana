# Development Support

Use Claude Code locally during implementation with the `dev-assist` profile. Claude Code is the preferred runner for this profile when working from the terminal.

Typical invocation sequence:
1. `scripts/run-profile.sh dev-assist --project-root .`
2. Ask Claude Code to invoke `change-impact-preview` with a description of the planned change.
3. Ask Claude Code to invoke `concurrency-risk` and `known-pitfalls-extraction` on the target class.
4. Review findings before writing any code.

Output artifacts go into `.mana/features/<FEATURE-ID>/agent-memory/`. Do not commit the workspace artifacts automatically.
