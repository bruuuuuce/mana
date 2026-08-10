import 'package:flutter_test/flutter_test.dart';
import 'package:mana_learning_explorer/investigation_inspector.dart';
import 'package:mana_learning_explorer/journey_graph.dart';

void main() {
  JourneyGraph graph() => JourneyGraph.decode('''
    {
      "nodes":[
        {"id":"current","label":"Service"},
        {"id":"next","label":"Repository"},
        {"id":"alternative","label":"Cache"},
        {"id":"later","label":"Migration"},
        {"id":"previous","label":"Controller"}
      ],
      "anchors":[{"id":"anchor","node_id":"current","revision":"abc123","path":"lib/service.dart","range":{"start_line":4,"end_line":8}}],
      "evidence":[
        {"id":"support","kind":"source_range","anchor_id":"anchor","summary":"Calls repository"},
        {"id":"contradiction","kind":"test","anchor_id":"anchor","summary":"Cache test disagrees"}
      ],
      "explanations":[{"subject_node_id":"current","body":"The service coordinates persistence.","evidence_ids":["support"]}],
      "hypotheses":[{"id":"hyp","subject_node_id":"current","claim":"The cache is optional.","confidence":"plausible","category":"compatibility_boundary","supports":["support"],"contradicts":["contradiction"]}],
      "edges":[
        {"from":"current","to":"next","kind":"CALLS","disposition":"primary"},
        {"from":"current","to":"alternative","kind":"CALLS","disposition":"alternative"},
        {"from":"current","to":"later","kind":"CALLS","disposition":"deferred"},
        {"from":"previous","to":"current","kind":"CALLS","disposition":"primary"}
      ]
    }
  ''');

  test(
    'resolves rationale, clickable evidence, and grouped semantic relations',
    () {
      final model = InvestigationInspectorModel.build(
        graph: graph(),
        nodeId: 'current',
        projectRoot: '/project',
      );

      expect(model.explanations.single['body'], contains('coordinates'));
      expect(model.hypotheses.single['claim'], contains('cache'));
      expect(model.evidence, hasLength(2));
      expect(model.evidence.first.location?.reference, 'lib/service.dart:4-8');
      expect(
        model.evidence.singleWhere((item) => item.id == 'support').relationship,
        'Supports hypothesis',
      );
      expect(
        model.evidence
            .singleWhere((item) => item.id == 'contradiction')
            .relationship,
        'Contradicts hypothesis',
      );
      expect(model.primary.single.label, 'Repository');
      expect(model.alternatives.single.label, 'Cache');
      expect(model.deferred.single.label, 'Migration');
      expect(model.cameFrom.single.label, 'Controller');
      expect(model.isTerminal, isFalse);
    },
  );

  test('reports terminal nodes instead of inventing a next hop', () {
    final model = InvestigationInspectorModel.build(
      graph: graph(),
      nodeId: 'next',
      projectRoot: '/project',
    );
    expect(model.isTerminal, isTrue);
    expect(model.primary, isEmpty);
  });
}
