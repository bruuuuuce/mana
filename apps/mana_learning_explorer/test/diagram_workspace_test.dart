import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mana_learning_explorer/diagram_detachment.dart';
import 'package:mana_learning_explorer/diagram_workspace.dart';
import 'package:mana_learning_explorer/explorer_navigation.dart';
import 'package:mana_learning_explorer/journey_graph.dart';

void main() {
  final graph = JourneyGraph.decode(
    '''{"journey":{"repository_revision":"snap"},"nodes":[{"id":"a"},{"id":"b"},{"id":"c"}],"edges":[{"id":"ab","from":"a","to":"b","kind":"CALLS"},{"id":"bc","from":"b","to":"c","kind":"CALLS"},{"id":"ca","from":"c","to":"a","kind":"LOOP_BACK"}]}''',
  );
  final diagram = <String, dynamic>{
    'id': 'sequence',
    'kind': 'sequence',
    'node_ids': ['a', 'b', 'c'],
  };

  test('creates finite structured bindings for a cyclic current path', () {
    final document = DiagramDocument.fromJourney(
      graph: graph,
      diagram: diagram,
      scope: DiagramScope.currentPath,
      currentNodeId: 'c',
    );
    expect(document.elements.map((element) => element.elementId), [
      'node:a',
      'node:b',
      'node:c',
    ]);
    expect(document.relations, hasLength(3));
    expect(document.provenance, 'snap');
  });

  test('bindings without targets stay metadata-only', () {
    const binding = DiagramElementBinding(elementId: 'fragment:alt');
    expect(binding.nodeIds, isEmpty);
    expect(binding.relationIds, isEmpty);
  });

  test('retains explicit multi-target bindings for the chooser', () {
    final document = DiagramDocument.fromJourney(
      graph: graph,
      diagram: {
        ...diagram,
        'elements': [
          {
            'id': 'fragment:choice',
            'node_ids': ['a', 'b'],
            'role': 'branch',
          },
        ],
      },
      scope: DiagramScope.wholeStream,
      currentNodeId: 'a',
    );
    expect(document.elements.single.nodeIds, ['a', 'b']);
  });

  testWidgets(
    'marks the current binding in text and moves between mapped steps',
    (tester) async {
      final route = ValueNotifier<ExplorerRoute?>(
        const ExplorerRoute(journeyId: 'journey', nodeId: 'c'),
      );
      final navigated = <ExplorerRoute>[];
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: DiagramWorkspace(
              graph: graph,
              diagrams: [diagram],
              currentRoute: route,
              onNavigate: navigated.add,
              windowState: DiagramWindowState(),
            ),
          ),
        ),
      );

      await tester.pump();
      expect(find.text('node:c • CURRENT'), findsOneWidget);
      await tester.tap(find.byTooltip('Previous mapped step (Alt+Left)'));
      expect(navigated.single.nodeId, 'b');
      route.dispose();
    },
  );
}
