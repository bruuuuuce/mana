import 'package:flutter_test/flutter_test.dart';
import 'package:mana_learning_explorer/architecture_context.dart';
import 'package:mana_learning_explorer/journey_graph.dart';

void main() {
  test(
    'uses explicit component and async execution bindings with provenance',
    () {
      final graph = JourneyGraph.decode('''
      {"journey":{"repository_revision":"journey-revision"},"nodes":[{"id":"node"}],"diagrams":[
        {"id":"component","kind":"component","node_ids":["node"],"elements":[{"id":"component-element","node_ids":["node"],"context":{"component":"billing-service","participant":"BillingWorker","execution_path":["HTTP","BillingWorker"],"step":"publish invoice","depth":2,"transition_kind":"async"},"provenance":{"snapshot":"analysis-42","confidence":"documented"}}]},
        {"id":"sequence","kind":"sequence","node_ids":["node"]}
      ]}
    ''');

      final model = ArchitectureContextModel.build(
        graph: graph,
        nodeId: 'node',
      );
      expect(model.status, ArchitectureContextStatus.mapped);
      expect(model.component, 'billing-service');
      expect(model.participant, 'BillingWorker');
      expect(model.executionPath, ['HTTP', 'BillingWorker']);
      expect(model.isAsync, isTrue);
      expect(model.provenance, 'analysis-42');
      expect(model.focusedElementId, 'component-element');
      expect(model.hasComponents, isTrue);
      expect(model.hasSequence, isTrue);
    },
  );

  test('does not fabricate semantics for unmapped or ambiguous diagrams', () {
    final partial = JourneyGraph.decode(
      '''{"nodes":[{"id":"node"}],"diagrams":[{"id":"diagram","kind":"sequence","node_ids":["node"]}]}''',
    );
    final ambiguous = JourneyGraph.decode('''
      {"nodes":[{"id":"node"}],"diagrams":[{"id":"diagram","kind":"sequence","node_ids":["node"],"elements":[{"id":"one","node_ids":["node"]},{"id":"two","node_ids":["node"]}]}]}
    ''');

    expect(
      ArchitectureContextModel.build(graph: partial, nodeId: 'node').status,
      ArchitectureContextStatus.partial,
    );
    final ambiguousModel = ArchitectureContextModel.build(
      graph: ambiguous,
      nodeId: 'node',
    );
    expect(ambiguousModel.status, ArchitectureContextStatus.ambiguous);
    expect(ambiguousModel.component, isNull);
    expect(ambiguousModel.executionPath, isEmpty);
  });

  test('states unavailable context honestly', () {
    final graph = JourneyGraph.decode('''{"nodes":[{"id":"node"}]}''');
    expect(
      ArchitectureContextModel.build(graph: graph, nodeId: 'node').status,
      ArchitectureContextStatus.unavailable,
    );
  });

  test('diagram view state is independent from route history', () {
    final state = DiagramViewState();
    state.focus('message-4');
    state.followCurrent = false;

    expect(state.focusedElementId, 'message-4');
    expect(state.followCurrent, isFalse);
    expect(state.kind, ArchitectureViewKind.components);
  });
}
