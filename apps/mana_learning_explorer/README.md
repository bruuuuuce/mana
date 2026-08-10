# Mana Learning Explorer

Read-only Flutter desktop client for an incremental Mana Journey.

```bash
cd apps/mana_learning_explorer
flutter run -d macos lib/main.dart -- --project-root /path/to/project --mana-root /path/to/mana --journey jrn_…
```

When run from this app directory inside a Mana repository, project and Mana
roots are discovered automatically; select a Journey from the dropdown.

The client invokes `mana-journey materialize` as its graph API and watches the
selected Journey directory. It never parses or writes Journey records itself.
It renders stable node navigation, source anchors, direct relations, concept
badges, explanation records and deferred nodes. “Request explanation” invokes
the existing bounded Expansion request command; it does not alter source code.

The local macOS runner deliberately has no App Sandbox entitlement: it needs
read access to the selected project’s `.mana` directory and source anchors.
This is a local developer tool, not an App Store-distributed application.
## Stress fixture

For manual review of branch, cycle, shared-target, terminal, no-source, and
source-authority states, launch the deterministic development-only fixture:

```sh
cd apps/mana_learning_explorer
flutter run -d macos -- --project-root ../.. --mana-root ../.. --fixture test/fixtures/complex_journey_fixture.json
```

The fixture is materialized Journey JSON, uses stable IDs, and does not alter
or persist data under `.mana`. Its alternative branch relies on the existing
Explorer `role: alternative` convention; the persisted Journey CLI does not
currently expose a corresponding `--role` option.
