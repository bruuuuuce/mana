import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mana_learning_explorer/architecture_context.dart';
import 'package:mana_learning_explorer/explorer_navigation.dart';
import 'package:mana_learning_explorer/graph_overview.dart';
import 'package:mana_learning_explorer/investigation_inspector.dart';
import 'package:mana_learning_explorer/journey_graph.dart';
import 'package:mana_learning_explorer/journey_navigator.dart';
import 'package:mana_learning_explorer/main.dart';
import 'package:mana_learning_explorer/source_workspace.dart';

const _fixturePath = 'test/fixtures/complex_journey_fixture.json';
const _journeyId = 'jrn_100000000000000000000001';
const _entry = 'jn_100000000000000000000001';
const _dispatch = 'jn_100000000000000000000002';
const _validate = 'jn_100000000000000000000003';
const _publish = 'jn_100000000000000000000004';
const _consume = 'jn_100000000000000000000005';
const _terminal = 'jn_100000000000000000000006';
const _retry = 'jn_100000000000000000000007';
const _alternative = 'jn_100000000000000000000008';
const _deferred = 'jn_100000000000000000000009';
const _context = 'jn_10000000000000000000000a';

JourneyGraph _fixture() =>
    JourneyGraph.decode(File(_fixturePath).readAsStringSync());

ExplorerRoute _route(
  String nodeId, {
  String? evidenceId,
  SourceLocation? source,
}) => ExplorerRoute(
  journeyId: _journeyId,
  nodeId: nodeId,
  evidenceId: evidenceId,
  sourceLocation: source,
);

void main() {
  test(
    'loads the deterministic stress fixture with unique finite topology',
    () {
      final graph = _fixture();
      final overview = GraphOverviewModel.build(graph);

      expect(graph.initialNodeId, _entry);
      expect(graph.nodes, hasLength(10));
      expect(graph.edges, hasLength(11));
      expect(overview.nodes.map((node) => node['id']).toSet(), hasLength(10));
      expect(overview.relations, hasLength(11));
      expect(overview.positions.keys, containsAll([_validate, _publish]));
      expect(
        overview.relations.where((edge) => edge.to == _publish),
        hasLength(2),
        reason: 'the shared publish target is topology, not two cloned nodes',
      );
    },
  );

  test('requires a primary choice and keeps secondary relations secondary', () {
    final graph = _fixture();
    final navigator = JourneyNavigatorModel.build(
      graph: graph,
      currentNodeId: _dispatch,
      visitedNodeIds: {_entry, _dispatch},
    );
    final inspector = InvestigationInspectorModel.build(
      graph: graph,
      nodeId: _dispatch,
      projectRoot: Directory.current.parent.parent.path,
    );

    expect(navigator.primary.map((item) => item.id), [_validate, _retry]);
    expect(inspector.primary, hasLength(2));
    expect(navigator.alternatives.single.id, _alternative);
    expect(navigator.deferred.single.id, _deferred);
    expect(navigator.related.single.id, _context);
    expect(
      inspector.primary.map((item) => item.targetId),
      isNot(contains(_deferred)),
    );
    expect(
      inspector.primary.map((item) => item.targetId),
      isNot(contains(_alternative)),
    );
  });

  test(
    'cycle visits stay finite while Back and Forward restore exact routes',
    () {
      final graph = _fixture();
      final topology = GraphOverviewModel.build(graph);
      final state = TraversalState()..reset(_route(_entry));
      for (final node in [
        _dispatch,
        _validate,
        _publish,
        _consume,
        _validate,
      ]) {
        state.navigate(_route(node));
      }

      expect(
        topology.nodes.where((node) => node['id'] == _validate),
        hasLength(1),
      );
      expect(state.backStack, hasLength(5));
      expect(state.current?.nodeId, _validate);
      expect(state.back()?.nodeId, _consume);
      expect(state.back()?.nodeId, _publish);
      expect(state.forward()?.nodeId, _consume);
      expect(state.forward()?.nodeId, _validate);
      expect(state.visitedNodeIds, {
        _entry,
        _dispatch,
        _validate,
        _publish,
        _consume,
      });
      expect(
        JourneyNavigatorModel.build(
          graph: graph,
          currentNodeId: _terminal,
          visitedNodeIds: state.visitedNodeIds,
        ).isTerminal,
        isTrue,
      );
    },
  );

  test(
    'resolves same-file and cross-file evidence without route divergence',
    () async {
      final graph = _fixture();
      final root = Directory.current.parent.parent.path;
      final dispatch = InvestigationInspectorModel.build(
        graph: graph,
        nodeId: _dispatch,
        projectRoot: root,
      );
      final consumer = InvestigationInspectorModel.build(
        graph: graph,
        nodeId: _consume,
        projectRoot: root,
      );
      final first = dispatch.evidence[0];
      final second = dispatch.evidence[1];
      final selected = _route(
        _dispatch,
        evidenceId: second.id,
        source: second.location,
      );
      final state = TraversalState()..reset(_route(_entry));
      state.navigate(selected);

      expect(
        first.location?.reference,
        'apps/mana_learning_explorer/lib/journey_graph.dart:1-24',
      );
      expect(
        second.location?.reference,
        'apps/mana_learning_explorer/lib/journey_graph.dart:35-58',
      );
      expect(
        consumer.evidence.single.location?.reference,
        'apps/mana_learning_explorer/lib/explorer_navigation.dart:1-42',
      );
      expect(state.current, selected);
      expect(state.current?.nodeId, _dispatch);
      expect(state.current?.sourceLocation, second.location);

      final authoritative = await SourceResolver().resolve(first.location!);
      expect(authoritative.state, SourceState.snapshot);
      expect(authoritative.available, isTrue);

      final retry = InvestigationInspectorModel.build(
        graph: graph,
        nodeId: _retry,
        projectRoot: root,
      );
      expect(retry.evidence.single.location, isNotNull);
      final resolved = await SourceResolver().resolve(
        retry.evidence.single.location!,
      );
      expect(resolved.state, SourceState.snapshotUnavailable);
      expect(resolved.available, isTrue);

      expect(
        graph.anchorsFor(_alternative),
        isEmpty,
        reason: 'the no-source state is explicit rather than fabricated',
      );
    },
  );

  test('keeps explicit architecture and event semantics honest', () {
    final graph = _fixture();
    final available = ArchitectureContextModel.build(
      graph: graph,
      nodeId: _dispatch,
    );
    final event = ArchitectureContextModel.build(
      graph: graph,
      nodeId: _publish,
    );
    final partial = ArchitectureContextModel.build(
      graph: graph,
      nodeId: _retry,
    );
    final unavailable = ArchitectureContextModel.build(
      graph: graph,
      nodeId: _terminal,
    );

    expect(available.status, ArchitectureContextStatus.mapped);
    expect(available.component, 'invoice-dispatcher');
    expect(event.isAsync, isTrue);
    expect(event.transitionKind, 'event');
    expect(partial.status, ArchitectureContextStatus.partial);
    expect(unavailable.status, ArchitectureContextStatus.unavailable);
  });

  test('loads the fixture through the development-only store option', () async {
    final store = JourneyStore(
      ExplorerConfig(
        projectRoot: Directory.current.parent.parent.path,
        manaRoot: Directory.current.parent.parent.path,
        fixturePath: _fixturePath,
      ),
    );
    expect(await store.list(), [_journeyId]);
    final graph = await store.load(_journeyId);
    expect(graph.nodes, hasLength(10));
    expect(await store.watch(_journeyId).isEmpty, isTrue);
    expect(
      await store.loadDiagram(_journeyId, graph.diagrams.first),
      contains('Invoice dispatch component context'),
    );
  });
}
