import 'package:flutter_test/flutter_test.dart';
import 'package:mana_learning_explorer/architecture_context.dart';
import 'package:mana_learning_explorer/diagram_detachment.dart';
import 'package:mana_learning_explorer/diagram_workspace.dart';
import 'package:mana_learning_explorer/explorer_navigation.dart';
import 'package:mana_learning_explorer/investigation_inspector.dart';
import 'package:mana_learning_explorer/journey_graph.dart';
import 'package:mana_learning_explorer/journey_navigator.dart';
import 'package:mana_learning_explorer/source_workspace.dart';

/// A workflow-level fixture: it deliberately contains a branch, a deferred
/// path, a loop, cross-file evidence, an async boundary, and both diagrams.
/// Keeping these scenarios together catches route contract regressions that
/// isolated widget/model tests cannot see.
final _graph = JourneyGraph.decode(r'''
{
  "journey":{"id":"guided","repository_revision":"snapshot-42"},
  "nodes":[
    {"id":"root","label":"HTTP entry"}, {"id":"service","label":"Billing service"},
    {"id":"persist","label":"Persist invoice"}, {"id":"retry","label":"Retry policy"},
    {"id":"deferred","label":"Backfill migration"}, {"id":"event","label":"Invoice event"},
    {"id":"consumer","label":"Notify customer"}, {"id":"terminal","label":"Done"}
  ],
  "edges":[
    {"id":"root-service","from":"root","to":"service","kind":"CALLS","disposition":"primary"},
    {"id":"service-persist","from":"service","to":"persist","kind":"CALLS","disposition":"primary"},
    {"id":"service-retry","from":"service","to":"retry","kind":"CALLS","disposition":"primary"},
    {"id":"service-deferred","from":"service","to":"deferred","kind":"CALLS","disposition":"deferred"},
    {"id":"persist-event","from":"persist","to":"event","kind":"EMITS","disposition":"primary"},
    {"id":"event-consumer","from":"event","to":"consumer","kind":"CONSUMES","disposition":"primary"},
    {"id":"consumer-service","from":"consumer","to":"service","kind":"LOOP_BACK","disposition":"alternative"},
    {"id":"consumer-terminal","from":"consumer","to":"terminal","kind":"CALLS","disposition":"primary"}
  ],
  "anchors":[
    {"id":"service-source","node_id":"service","path":"lib/billing.dart","revision":"snapshot-42","range":{"start_line":10,"end_line":14}},
    {"id":"consumer-source","node_id":"consumer","path":"lib/notify.dart","revision":"snapshot-42","range":{"start_line":31,"end_line":35}}
  ],
  "evidence":[
    {"id":"service-evidence","anchor_id":"service-source","kind":"source_range","summary":"Chooses persistence or retry."},
    {"id":"consumer-evidence","anchor_id":"consumer-source","kind":"source_range","summary":"Publishes notification."}
  ],
  "explanations":[{"subject_node_id":"service","body":"Service dispatches the invoice.","evidence_ids":["service-evidence"]}],
  "diagrams":[
    {"id":"components","kind":"component","node_ids":["root","service","persist","retry","deferred","event","consumer","terminal"],"elements":[
      {"id":"billing-component","node_ids":["service"],"role":"component","context":{"component":"billing","participant":"BillingService","execution_path":["HTTP","BillingService"],"step":"dispatch invoice","depth":1}},
      {"id":"ambiguous-storage","node_ids":["persist","retry"],"role":"component"},
      {"id":"legend","node_ids":[],"role":"metadata"}
    ]},
    {"id":"sequence","kind":"sequence","node_ids":["root","service","persist","retry","deferred","event","consumer","terminal"],"elements":[
      {"id":"publish-message","node_ids":["event"],"role":"message","context":{"component":"event-bus","participant":"InvoiceTopic","execution_path":["BillingService","InvoiceTopic"],"step":"invoice published","depth":2,"transition_kind":"event"}},
      {"id":"consumer-message","node_ids":["consumer"],"role":"message","context":{"component":"notifier","participant":"NotificationWorker","execution_path":["InvoiceTopic","NotificationWorker"],"step":"notify customer","depth":3,"transition_kind":"async"}}
    ]}
  ]
}
''');

ExplorerRoute _route(
  String node, {
  String? evidenceId,
  SourceLocation? source,
}) => ExplorerRoute(
  journeyId: 'guided',
  nodeId: node,
  evidenceId: evidenceId,
  sourceLocation: source,
);

void main() {
  test(
    'guided route keeps navigator, evidence, inspector, and context aligned',
    () {
      expect(_graph.initialNodeId, 'root');
      final traversal = TraversalState()..reset(_route('root'));
      expect(traversal.current, _route('root'));

      final serviceInspector = InvestigationInspectorModel.build(
        graph: _graph,
        nodeId: 'service',
        projectRoot: '/project',
      );
      final evidence = serviceInspector.evidence.single;
      final evidenceRoute = _route(
        'service',
        evidenceId: evidence.id,
        source: evidence.location,
      );
      traversal.navigate(evidenceRoute);
      expect(
        traversal.current?.sourceLocation?.reference,
        'lib/billing.dart:10-14',
      );

      // Two primary branches require a choice; the deferred path is available
      // but never included in the promoted primary group.
      expect(serviceInspector.primary.map((item) => item.targetId), [
        'persist',
        'retry',
      ]);
      expect(serviceInspector.deferred.single.targetId, 'deferred');

      final persisted = _route('persist');
      traversal.navigate(persisted);
      expect(_snapshot(persisted).nodeId, 'persist');
      expect(_snapshot(persisted).inspector.primary.single.targetId, 'event');

      expect(traversal.back(), evidenceRoute);
      expect(
        _snapshot(traversal.current!).source.reference,
        'lib/billing.dart:10-14',
      );
      expect(_snapshot(traversal.current!).context.component, 'billing');
      expect(traversal.forward(), persisted);
      expect(
        _snapshot(traversal.current!).context.focusedElementId,
        'ambiguous-storage',
      );
    },
  );

  test(
    'cycles, cross-file evidence, terminal nodes, and async context remain honest',
    () {
      final traversal = TraversalState()..reset(_route('service'));
      for (final node in ['persist', 'event', 'consumer', 'service']) {
        traversal.navigate(_route(node));
      }
      final navigator = JourneyNavigatorModel.build(
        graph: _graph,
        currentNodeId: 'service',
        visitedNodeIds: traversal.visitedNodeIds,
      );
      expect(navigator.currentPath.map((item) => item.id), ['root', 'service']);
      expect(traversal.backStack, hasLength(4));

      final consumerEvidence = InvestigationInspectorModel.build(
        graph: _graph,
        nodeId: 'consumer',
        projectRoot: '/project',
      ).evidence.single;
      expect(consumerEvidence.location?.reference, 'lib/notify.dart:31-35');
      final asyncContext = _snapshot(_route('consumer')).context;
      expect(asyncContext.isAsync, isTrue);
      expect(asyncContext.executionPath, [
        'InvoiceTopic',
        'NotificationWorker',
      ]);
      expect(asyncContext.status, ArchitectureContextStatus.mapped);

      final terminal = _snapshot(_route('terminal')).inspector;
      expect(terminal.isTerminal, isTrue);
      expect(terminal.primary, isEmpty);
    },
  );

  test(
    'diagram bindings preserve explicit navigation, scope, follow, and detached-window contracts',
    () {
      final component = _graph.diagrams.singleWhere(
        (item) => item['id'] == 'components',
      );
      final sequence = _graph.diagrams.singleWhere(
        (item) => item['id'] == 'sequence',
      );
      final route = _route('service');
      final componentDocument = DiagramDocument.fromJourney(
        graph: _graph,
        diagram: component,
        scope: DiagramScope.wholeStream,
        currentNodeId: route.nodeId,
      );
      expect(
        componentDocument.elements
            .singleWhere((item) => item.elementId == 'billing-component')
            .nodeIds,
        ['service'],
      );
      expect(
        componentDocument.elements
            .singleWhere((item) => item.elementId == 'ambiguous-storage')
            .nodeIds,
        ['persist', 'retry'],
      );
      expect(
        componentDocument.elements
            .singleWhere((item) => item.elementId == 'legend')
            .nodeIds,
        isEmpty,
      );

      for (final scope in DiagramScope.values) {
        final document = DiagramDocument.fromJourney(
          graph: _graph,
          diagram: sequence,
          scope: scope,
          currentNodeId: 'consumer',
        );
        expect(document.id, 'sequence');
        expect(
          document.elements.every((item) => item.elementId.isNotEmpty),
          isTrue,
        );
      }

      final view = DiagramViewState()..followCurrent = false;
      view.focus('consumer-message');
      expect(view.focusedElementId, 'consumer-message');
      expect(view.followCurrent, isFalse);

      final window = DiagramWindowState();
      expect(
        window.requestDetach(DiagramDetachmentCapability.unavailable),
        isFalse,
      );
      expect(window.value, isFalse);
      // An unavailable native bridge must not fork session/history state.
      final traversal = TraversalState()..reset(route);
      traversal.navigate(_route('event'));
      expect(traversal.back(), route);
    },
  );
}

class _RouteSnapshot {
  const _RouteSnapshot({
    required this.nodeId,
    required this.source,
    required this.inspector,
    required this.context,
  });

  final String nodeId;
  final SourceLocation source;
  final InvestigationInspectorModel inspector;
  final ArchitectureContextModel context;
}

_RouteSnapshot _snapshot(ExplorerRoute route) {
  final inspector = InvestigationInspectorModel.build(
    graph: _graph,
    nodeId: route.nodeId,
    projectRoot: '/project',
  );
  final source =
      route.sourceLocation ??
      inspector.evidence.firstOrNull?.location ??
      const SourceLocation(
        projectRoot: '/project',
        path: 'unknown',
        startLine: 1,
        endLine: 1,
      );
  return _RouteSnapshot(
    nodeId: route.nodeId,
    source: source,
    inspector: inspector,
    context: ArchitectureContextModel.build(
      graph: _graph,
      nodeId: route.nodeId,
    ),
  );
}
