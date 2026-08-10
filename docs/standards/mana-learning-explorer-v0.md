# Mana Learning Explorer v0

The Flutter client in `apps/mana_learning_explorer` is a read-only renderer of
incremental Journey state. Mana remains authoritative for IDs, persistence,
materialization, evidence and expansion semantics.

The app invokes `scripts/mana-journey.sh materialize` and watches the selected
Journey directory with `Directory.watch(recursive: true)`. Every filesystem
event reloads the materialized graph; no restart or Journey regeneration is
needed when Mana appends records.

The initial UI deliberately uses a simple three-panel layout: stable Journey
node navigation, node/enrichment details, and an anchor-highlighted source
viewer. It renders deferred branches, direct paths, canonical concept badges,
explanation bodies, scoped Git timeline events and a bounded “Request
explanation” action. The action
delegates to Phase 5’s request CLI; it never writes source code or Journey
records directly. For an explicitly generated diagram, it opens the derived
PlantUML source beside the selected Journey node; the embedded node IDs allow
the user to return to that node and its source anchors.

Run it with:

```bash
cd apps/mana_learning_explorer
flutter run -d macos lib/main.dart -- --project-root /path/to/project --mana-root /path/to/mana --journey jrn_…
```
