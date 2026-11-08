# Dynamic Model Resolution

MANA resolves provider models by requested capability tier before it builds
invocation arguments. The public result is `mana.model-resolution/v1`; see
`contracts/model-resolution-v1.schema.json`. Diagnostics include whether MANA
supports execution for that provider; Junie discovery is supported while
execution through MANA is explicitly unsupported.

Use `python3 scripts/mana-models.py doctor --provider codex --tier economy
--json` to inspect a resolution without inference. Providers that expose a
catalog are queried on demand through their CLI or supported discovery
protocol. `--refresh` asks OpenCode to refresh its provider catalog; Codex
`model/list` is queried live. MANA does not cache catalogs, so there are no
stale or cross-account cached selections to reuse. Use `--fixture path.json`
to run deterministic discovery tests without credentials or paid calls.

Pin precedence is command-line `--model`, then the provider's `MANA_*_MODEL`
setting, then the provider-native project/account default. Junie also honors
`JUNIE_MODEL` when `MANA_JUNIE_MODEL` is unset. When discovery shows that a pin
is unavailable, MANA blocks and does not substitute another model. For tiers
without enough identity or eligibility evidence, MANA reports the uncertainty
and blocks high-risk escalation. Discovery
failure is distinct from invocation rejection; the resolver never retries a
provider call or switches providers.

Claude Code supports dynamic `haiku`, `sonnet`, and `opus` family aliases. The
aliases avoid release-specific IDs but do not prove account entitlement or
quality for every task. MANA blocks Claude routing when its CLI is not installed.
Requested effort is checked against the selected family before invocation:
Haiku has no supported effort setting, Sonnet supports `low`, `medium`, and
`high`, and Opus supports `low`, `medium`, `high`, `xhigh`, and `max`. A CLI
flag's presence alone does not establish model-specific support, so unsupported
or unverified model/effort pairs block.
OpenCode discovery reads the active provider-scoped catalog and resolved
project default, preserving the complete provider/model identity and
advertised variants. The provider prefix is part of that identity: a provider
change for the same model family is a different route and may have different
entitlement, billing, or terms. The full-tier family rule grants semantic
eligibility only; it does not authorize MANA to switch OpenCode providers,
rewrite project configuration, or assume equivalent billing. Automatic full-
tier selection stays within the provider of the active project default; an
explicit provider/model pin can request another route and still must pass the
same full-tier eligibility policy. OpenCode defines route identity as
`provider/model` ([model selection](https://opencode.ai/docs/models/)). In
particular, `opencode/<model-id>` selects OpenCode Console, whose published
flow requires account credits and charges per request ([Console models](https://opencode.ai/docs/console/models/)); MANA must not silently substitute
it for another provider route. A
missing project default can use OpenCode's provider-native default for low-risk
requests with no effort requirement, while
reporting that the exact identity is unknown. Explicit inactive pins block.
Listing and variant metadata do not prove a full-tier capability. Codex discovery uses the
App Server `model/list` interface when available and reads visibility,
reasoning-effort, default, and upgrade metadata. Catalog membership is not
entitlement proof, and an upgrade hint does not itself prove full-tier
capability. If Codex model/list is unsupported, MANA leaves the model ID unset
and lets Codex use its provider-owned default for requests without a required
reasoning effort, and only for economy or standard tiers. Full-tier resolution
requires a discovered model identity that matches the explicit, versioned
family eligibility policy in `config/model-tier-eligibility-v1.json` and
advertises the required effort. Catalog presence and recency do not grant
eligibility; discovery chooses the highest numeric version only within an
approved family. Claude's dynamic `opus` alias and OpenCode variants are
subject to their corresponding explicit policy rules. A pin outside the policy
blocks without substitution. Before querying its catalog, Codex opts out of automatic
gateway OAuth browser login and checks the read-only gateway credential status;
catalog discovery blocks unless required credentials are ready. Authentication
errors and unsupported explicit efforts do not take the provider-default
fallback. Junie accepts `--model` and `--effort`, documents a
dynamic `Default`, documented model aliases, and custom profiles in `.junie/models` and
`$JUNIE_HOME/models`. MANA reports those identities without exposing profile
contents; it cannot verify account entitlement or custom endpoint reachability
noninteractively. It uses `Default` for ordinary automatic resolution and
blocks automatic full-tier selection. Junie execution through MANA remains
unsupported.

Resolution's `selectedModel` and `availability` describe model identity and
catalog evidence; `accountAvailability` remains `unknown` until the provider
checks entitlement. `executionStatus: not_invoked` means a doctor/selection
result did not make an inference call. Selection, account availability, and
actual execution are separate facts.

Model tiers are semantic selection policy only. They do not grant tool,
filesystem, provider, or external-write permissions and do not increase cost
ceilings. Economy and standard may resolve to the same full-tier model, and
neither tier guarantees a lower-cost model. The provider remains responsible
for entitlement checks at invocation time. MANA does not persist catalog data
or credentials.

Diagnostics keep `supportedReasoningEfforts` limited to values accepted by the
MANA dispatch contract. `observedReasoningEfforts` retains provider-reported
values, including unknown values such as `ultra`, with the model identity and
discovery source. Unknown observations remain unavailable for dispatch until
the contract and policy explicitly support them.

The production Context Runtime worker-routing policy leaves `modelId` null so
the provider-boundary resolver owns identity selection. Workers resolve the
provider, semantic tier, and requested effort before constructing provider
arguments; OpenCode receives only a catalog-advertised variant. A null packet
identity is not an instruction to invoke a provider's unverified default.
Full-tier capability must resolve before MANA installs a specialist agent or
dispatches a high-risk stage. Fixture worker identities remain fixed by their
test-only routing policy.

## Fixture verification

Run `tests/model-resolution.sh` and `tests/codex-subagent-regression.sh` for
local-only checks covering new model discovery and full-tier selection,
eligibility blocking, provider-native fallback boundaries, explicit pins, and
separation of selection, account availability, and execution evidence.
