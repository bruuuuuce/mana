# Mana Familiar Inspect v1 Handoff

The canonical, copyable consumer bundle is
[`contracts/mana-inspect/v1/`](../../contracts/mana-inspect/v1/). Mana owns the
schemas, fixtures, vocabulary, and compatibility policy; Mana Familiar owns
only UI presentation, navigation, and local preferences.

Invoke a linked producer through its public wrapper:

```sh
./mana inspect project --json
./mana inspect artifacts --json
./mana inspect artifact <artifact-id> --json
./mana inspect source <project-relative-source-path> --json
```

Negotiate `project` and `artifacts` as the minimum capability. Treat `artifact`
and `source` as optional. Preserve unknown catalog entries and unknown object
fields without attempting to parse their contents; show a safe unavailable
state for unsupported schemas, malformed artifacts, and non-zero exits.

Journey graph rendering remains on the existing `mana.learning.graph/v1`
materialization API. Inspect adds catalog/detail/source navigation and does not
replace Journey materialization. Familiar must not import `scripts/`, parse
`.mana` layouts itself, access absolute paths, execute payload commands, or
depend on Mana's source checkout after copying/releasing this bundle.

For a zero-token consumer preflight, run:

```sh
/path/to/mana/scripts/validate-inspect-contract.sh \
  --bundle /path/to/copied/mana-inspect/v1
```

This validates static schemas and fixtures only; it makes no network or model
call and does not write a project workspace.
