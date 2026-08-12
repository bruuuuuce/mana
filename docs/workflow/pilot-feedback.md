# Pilot feedback: internal procedure

`mana pilot-feedback` measures whether a human says a Mana finding changed a
review decision. It is optional, local-only, and produces no runtime telemetry,
network traffic, model call, dashboard, time-saving estimate, or individual
performance metric.

## For internal pilot testers

1. Review a finding normally. Use an opaque run/finding reference already shown
   in the local report; do not paste source, ticket bodies, URLs, names, or
   credentials.
2. Record one human disposition per run/finding/profile:

   ```bash
   ./mana pilot-feedback record --run-ref run-42 --finding-ref finding-7 \
     --profile requested-pr-review --disposition accepted \
     --changed-before-pr yes --would-reviewer-find-anyway maybe --reason bug \
     --note "Added regression test"
   ```

3. Generate a shareable aggregate only when authorized:

   ```bash
   ./mana pilot-feedback report --json
   ./mana pilot-feedback report --csv
   ./mana pilot-feedback report --markdown
   ```

Raw records remain in `.mana/pilot-feedback/records/`; aggregate exports in
`.mana/pilot-feedback/reports/` contain counts and rates only. They omit source
content, URLs, company names, employee identities, credentials, Jira bodies,
and raw notes. Share only the aggregate after the relevant internal approval.

## Interpretation

The report provides clear denominators for reviewed runs, dispositioned
findings, accepted rate, false-positive/rejected rate, changes before PR, and
unknown fields. It cannot prove saved time, ROI, correctness, adoption, or why
an unrecorded finding has no feedback. Use it as C02 input alongside human
pilot notes, not as an automated go/no-go decision.
