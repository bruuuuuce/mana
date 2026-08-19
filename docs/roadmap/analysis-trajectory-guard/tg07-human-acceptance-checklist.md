# TG07 human acceptance checklist

Complete this once for each comparable off/shadow/enforce story set. Record the
story-context hash rather than story text.

- Reviewer(s):
- Role(s): chief / architect / implementation reviewer:
- Repository revision:
- Story-context hash:
- Provider and printed stage routes:
- Pilot artifact directory:
- Review date:

- [ ] Did the guarded run retain every fact necessary to implement the story correctly?
- [ ] Did it miss a mandatory dependency or constraint?
- [ ] Did it stop useful investigation too early?
- [ ] Did it investigate a real but unrelated bug too deeply?
- [ ] Was every scope expansion understandable and explicit?
- [ ] Were open decisions preserved as decisions rather than silently selected?
- [ ] Was the re-anchor recommendation actionable and linked to an active goal, constraint, or gap?
- [ ] Was the final evidence package more focused than the unguarded one without losing necessary evidence?
- [ ] Did the checkpoint overhead justify the improvement?
- [ ] Would the reviewer trust shadow mode on additional stories?
- [ ] Would the reviewer trust enforce mode? If yes, under which explicit limits and owner-review conditions?

Record quantitative judgments:

- Mandatory evidence expected / retained:
- Useful investigation stopped too early (count and refs):
- Unrelated investigation continued too deeply (count and refs):
- Re-anchor accepted / rejected and reason:
- Scope-expansion proposal accepted / rejected / deferred and reason:
- Preferred evidence package: off / shadow / enforce / no preference:
- Checkpoint calls and reported token usage or proxy:
- Human false re-anchor:
- Human false stop:

Final disposition (select one):

- [ ] `NOT_READY`
- [ ] `SHADOW_PILOT_ONLY`
- [ ] `ENFORCE_PILOT_WITH_OWNER_REVIEW`
- [ ] `READY_FOR_BOUNDED_DEFAULT`

List unresolved risks, approved limits, required follow-up, and reviewer
sign-off. A checked deterministic test, schema-valid response, or lower token
proxy is not a substitute for this human decision.
