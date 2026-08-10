import 'package:flutter_test/flutter_test.dart';
import 'package:mana_learning_explorer/journey_graph.dart';
import 'package:mana_learning_explorer/journey_navigator.dart';

void main() {
  JourneyGraph graph() => JourneyGraph.decode('''
    {
      "nodes":[
        {"id":"start","label":"Start","state":"expanded"},
        {"id":"main","label":"Main path","state":"discovered"},
        {"id":"choice","label":"Primary choice","state":"discovered"},
        {"id":"alt","label":"Alternative","state":"discovered"},
        {"id":"later","label":"Deferred work","state":"discovered"},
        {"id":"related","label":"Related context","state":"discovered"},
        {"id":"other","label":"Other known node","state":"discovered"}
      ],
      "edges":[
        {"from":"start","to":"main","kind":"CALLS","disposition":"primary"},
        {"from":"main","to":"choice","kind":"CALLS","disposition":"primary"},
        {"from":"main","to":"alt","kind":"CALLS","disposition":"alternative"},
        {"from":"main","to":"later","kind":"CALLS","disposition":"deferred"},
        {"from":"main","to":"related","kind":"RELATED_TO","disposition":"primary"},
        {"from":"choice","to":"main","kind":"LOOP_BACK","disposition":"primary"}
      ]
    }
  ''');

  test(
    'groups guided next hops without hiding alternatives or deferred paths',
    () {
      final model = JourneyNavigatorModel.build(
        graph: graph(),
        currentNodeId: 'main',
        visitedNodeIds: {'start', 'main'},
      );

      expect(model.currentPath.map((item) => item.id), ['start', 'main']);
      expect(model.primary.single.id, 'choice');
      expect(model.alternatives.single.id, 'alt');
      expect(model.deferred.single.id, 'later');
      expect(model.related.single.id, 'related');
      expect(model.explorable.single.id, 'other');
      expect(model.isTerminal, isFalse);
    },
  );

  test(
    'cycle projection is finite and a node with no outgoing edges is terminal',
    () {
      final model = JourneyNavigatorModel.build(
        graph: graph(),
        currentNodeId: 'choice',
        visitedNodeIds: {'start', 'main', 'choice'},
      );
      final terminal = JourneyNavigatorModel.build(
        graph: graph(),
        currentNodeId: 'other',
        visitedNodeIds: {'other'},
      );

      expect(model.currentPath.map((item) => item.id), [
        'start',
        'main',
        'choice',
      ]);
      expect(model.primary.single.id, 'main');
      expect(terminal.isTerminal, isTrue);
    },
  );
}
