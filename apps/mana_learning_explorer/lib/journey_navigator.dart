import 'journey_graph.dart';

enum JourneyPathRole { primary, alternative, deferred, related }

class JourneyNavigatorItem {
  const JourneyNavigatorItem({
    required this.node,
    required this.role,
    required this.isCurrent,
    required this.isVisited,
    required this.relationHint,
  });

  final Map<String, dynamic> node;
  final JourneyPathRole role;
  final bool isCurrent;
  final bool isVisited;
  final String? relationHint;

  String get id => node['id'] as String;
  String get label => node['label'] as String? ?? id;
  String get state => node['state'] as String? ?? 'discovered';
}

/// A finite projection of the graph for guided exploration. It contains no
/// recursive graph expansion, so cyclic Journeys remain straightforward.
class JourneyNavigatorModel {
  JourneyNavigatorModel({
    required this.currentPath,
    required this.primary,
    required this.alternatives,
    required this.deferred,
    required this.related,
    required this.visitedOutsidePath,
    required this.explorable,
    required this.isTerminal,
  });

  final List<JourneyNavigatorItem> currentPath;
  final List<JourneyNavigatorItem> primary;
  final List<JourneyNavigatorItem> alternatives;
  final List<JourneyNavigatorItem> deferred;
  final List<JourneyNavigatorItem> related;
  final List<JourneyNavigatorItem> visitedOutsidePath;
  final List<JourneyNavigatorItem> explorable;
  final bool isTerminal;

  factory JourneyNavigatorModel.build({
    required JourneyGraph graph,
    required String currentNodeId,
    required Set<String> visitedNodeIds,
  }) {
    JourneyNavigatorItem item(String id, JourneyPathRole role) {
      final node = graph.node(id)!;
      final incoming = graph.incoming(id);
      final outgoing = graph.outgoing(id);
      return JourneyNavigatorItem(
        node: node,
        role: role,
        isCurrent: id == currentNodeId,
        isVisited: visitedNodeIds.contains(id),
        relationHint: outgoing.isNotEmpty
            ? '${outgoing.length} outgoing'
            : incoming.isNotEmpty
            ? 'from ${incoming.first['kind'] ?? 'relation'}'
            : null,
      );
    }

    final pathIds = graph.logicalPathFor(currentNodeId);
    final path = pathIds
        .where((id) => graph.node(id) != null)
        .map((id) => item(id, JourneyPathRole.primary))
        .toList();
    final outgoing = graph.outgoing(currentNodeId);
    final primary = <JourneyNavigatorItem>[];
    final alternatives = <JourneyNavigatorItem>[];
    final deferred = <JourneyNavigatorItem>[];
    final related = <JourneyNavigatorItem>[];
    for (final edge in outgoing) {
      final target = edge['to'] as String?;
      if (target == null || graph.node(target) == null) continue;
      switch (_roleFor(edge)) {
        case JourneyPathRole.primary:
          primary.add(item(target, JourneyPathRole.primary));
        case JourneyPathRole.alternative:
          alternatives.add(item(target, JourneyPathRole.alternative));
        case JourneyPathRole.deferred:
          deferred.add(item(target, JourneyPathRole.deferred));
        case JourneyPathRole.related:
          related.add(item(target, JourneyPathRole.related));
      }
    }
    final pathSet = pathIds.toSet();
    final knownTargets = outgoing
        .map((edge) => edge['to'] as String?)
        .whereType<String>()
        .toSet();
    final visited = graph.nodes
        .where((node) {
          final id = node['id'] as String;
          return visitedNodeIds.contains(id) && !pathSet.contains(id);
        })
        .map((node) => item(node['id'] as String, JourneyPathRole.related))
        .toList();
    final explorable = graph.nodes
        .where((node) {
          final id = node['id'] as String;
          return !pathSet.contains(id) &&
              !visitedNodeIds.contains(id) &&
              !knownTargets.contains(id);
        })
        .map((node) => item(node['id'] as String, JourneyPathRole.related))
        .toList();
    return JourneyNavigatorModel(
      currentPath: path,
      primary: primary,
      alternatives: alternatives,
      deferred: deferred,
      related: related,
      visitedOutsidePath: visited,
      explorable: explorable,
      isTerminal: outgoing.isEmpty,
    );
  }

  static JourneyPathRole _roleFor(Map<String, dynamic> edge) {
    final disposition = edge['disposition'] as String? ?? 'primary';
    if (disposition == 'deferred') return JourneyPathRole.deferred;
    if (disposition == 'alternative' || edge['role'] == 'alternative') {
      return JourneyPathRole.alternative;
    }
    if ((edge['kind'] as String?) == 'RELATED_TO') {
      return JourneyPathRole.related;
    }
    return JourneyPathRole.primary;
  }
}
