import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mana_learning_explorer/journey_graph.dart';
import 'package:mana_learning_explorer/main.dart';

void main() {
  test('keeps graph navigation and enrichments scoped to a stable node', () {
    final graph = JourneyGraph.decode(
      '''{"journey":{"title":"Payment"},"nodes":[{"id":"jn_a","label":"Service"},{"id":"jn_b","label":"Repository"}],"edges":[{"id":"je_a","from":"jn_a","to":"jn_b","kind":"CALLS"}],"anchors":[{"id":"anc_a","node_id":"jn_a","path":"src/Service.java","range":{"start_line":2,"end_line":4}}],"explanations":[{"id":"exp_a","subject_node_id":"jn_a"}],"concept_occurrences":[{"id":"occ_a","subject_node_id":"jn_a","concept_id":"cpt_001"}],"timeline_events":[{"id":"tle_a","subject_node_id":"jn_a","occurred_at":"2026-01-02T00:00:00Z"},{"id":"tle_b","subject_node_id":"jn_a","occurred_at":"2026-01-03T00:00:00Z"}],"diagrams":[{"id":"dia_a","kind":"sequence","asset_path":"assets/sequence.puml","node_ids":["jn_a","jn_b"]}]}''',
    );
    expect(graph.title, 'Payment');
    expect(graph.anchorsFor('jn_a'), hasLength(1));
    expect(graph.related('jn_a'), hasLength(1));
    expect(graph.explanationsFor('jn_a'), hasLength(1));
    expect(graph.conceptsFor('jn_a').single['concept_id'], 'cpt_001');
    expect(graph.timelineFor('jn_a').first['id'], 'tle_b');
    expect(graph.diagramsFor('jn_a').single['id'], 'dia_a');
    expect(graph.node('jn_b')?['label'], 'Repository');
  });

  test('builds a finite logical breadcrumb from primary graph relations', () {
    final graph = JourneyGraph.decode(
      '''{"nodes":[{"id":"a"},{"id":"b"},{"id":"c"}],"edges":[{"from":"a","to":"b","disposition":"primary"},{"from":"b","to":"c","disposition":"primary"},{"from":"c","to":"a","disposition":"primary"}]}''',
    );

    expect(graph.logicalPathFor('c'), ['a', 'b', 'c']);
  });

  test('prefers the declared traversal entry over serialized node order', () {
    final graph = JourneyGraph.decode('''
      {"nodes":[{"id":"later"},{"id":"entry"},{"id":"other"}],
       "traversals":[{"entry_node_id":"entry","node_ids":["entry","later"]}],
       "edges":[{"from":"entry","to":"later","disposition":"primary"}]}
    ''');

    expect(graph.initialNodeId, 'entry');
  });

  test('watches append-only Journey record changes', () async {
    final root = await Directory.systemTemp.createTemp('mana-explorer-watch-');
    addTearDown(() => root.delete(recursive: true));
    const journey = 'jrn_0123456789abcdef01234567';
    final records = Directory(
      '${root.path}/project/.mana/learning/journeys/$journey/records',
    );
    await records.create(recursive: true);
    final store = JourneyStore(
      ExplorerConfig(projectRoot: '${root.path}/project', manaRoot: root.path),
    );
    final event = store.watch(journey).first;
    await File(
      '${records.path}/jn_0123456789abcdef01234567-node.yaml',
    ).writeAsString('{}');
    await event.timeout(const Duration(seconds: 2));
  });

  test(
    'discovers the Mana repository when launched from the app directory',
    () {
      final config = ExplorerConfig.parse(const []);
      expect(Directory('${config.projectRoot}/.mana').existsSync(), isTrue);
      expect(
        File('${config.manaRoot}/scripts/mana-journey.sh').existsSync(),
        isTrue,
      );
    },
  );

  test(
    'persists the selected theme mode in project-local explorer settings',
    () async {
      final root = await Directory.systemTemp.createTemp(
        'mana-explorer-theme-',
      );
      addTearDown(() => root.delete(recursive: true));
      final config = ExplorerConfig(
        projectRoot: root.path,
        manaRoot: root.path,
      );

      final preferences = await ExplorerPreferences.load(config);
      expect(preferences.themeMode.value, ThemeMode.system);
      await preferences.saveThemeMode(ThemeMode.dark);
      await preferences.saveDisplay(fontSize: 18, tabSize: 4, wordWrap: true);

      final reloaded = await ExplorerPreferences.load(config);
      expect(reloaded.themeMode.value, ThemeMode.dark);
      expect(reloaded.fontSize, 18);
      expect(reloaded.tabSize, 4);
      expect(reloaded.wordWrap, isTrue);
    },
  );
}
