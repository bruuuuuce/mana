import 'package:flutter_test/flutter_test.dart';
import 'package:mana_learning_explorer/graph_overview.dart';
import 'package:mana_learning_explorer/journey_graph.dart';

void main() {
  test('projects each cyclic node once and preserves semantic edge styles', () {
    final graph = JourneyGraph.decode('''
      {"nodes":[{"id":"a"},{"id":"b"},{"id":"c"},{"id":"d"}],
       "edges":[
        {"id":"primary","from":"a","to":"b","kind":"CALLS","disposition":"primary"},
        {"id":"alternative","from":"b","to":"c","kind":"CALLS","disposition":"alternative"},
        {"id":"deferred","from":"b","to":"d","kind":"CALLS","disposition":"deferred"},
        {"id":"cycle","from":"c","to":"a","kind":"RELATED_TO"}
       ]}
    ''');
    final model = GraphOverviewModel.build(graph);
    expect(model.nodes, hasLength(4));
    expect(model.positions.keys.toSet(), {'a', 'b', 'c', 'd'});
    expect(
      model.relations.map((edge) => edge.style),
      containsAll([
        GraphRelationStyle.primary,
        GraphRelationStyle.alternative,
        GraphRelationStyle.deferred,
        GraphRelationStyle.related,
      ]),
    );
  });

  test('remains finite for a realistically large graph fixture', () {
    final nodes = List.generate(
      480,
      (index) => '{"id":"node-$index"}',
    ).join(',');
    final edges = List.generate(520, (index) {
      final from = index % 480;
      final to = (index + 1) % 480;
      return '{"id":"edge-$index","from":"node-$from","to":"node-$to","kind":"CALLS","disposition":"${index.isEven ? 'primary' : 'alternative'}"}';
    }).join(',');
    final model = GraphOverviewModel.build(
      JourneyGraph.decode('{"nodes":[$nodes],"edges":[$edges]}'),
    );
    expect(model.nodes, hasLength(480));
    expect(model.relations, hasLength(520));
  });
}
