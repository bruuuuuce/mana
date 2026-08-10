import 'dart:convert';

class JourneyGraph {
  JourneyGraph(this.raw);
  final Map<String, dynamic> raw;

  String get title => raw['journey']?['title'] as String? ?? 'Untitled Journey';
  List<Map<String, dynamic>> get nodes => _records('nodes');
  List<Map<String, dynamic>> get edges => _records('edges');
  List<Map<String, dynamic>> get anchors => _records('anchors');
  List<Map<String, dynamic>> get evidence => _records('evidence');
  List<Map<String, dynamic>> get explanations => _records('explanations');
  List<Map<String, dynamic>> get hypotheses => _records('hypotheses');
  List<Map<String, dynamic>> get hypothesisAssessments =>
      _records('hypothesis_assessments');
  List<Map<String, dynamic>> get occurrences => _records('concept_occurrences');
  List<Map<String, dynamic>> get timelineEvents => _records('timeline_events');
  List<Map<String, dynamic>> get diagrams => _records('diagrams');
  List<Map<String, dynamic>> get traversals => _records('traversals');

  List<Map<String, dynamic>> _records(String key) =>
      ((raw[key] as List<dynamic>? ?? const [])).cast<Map<String, dynamic>>();
  Map<String, dynamic>? node(String id) {
    for (final item in nodes) {
      if (item['id'] == id) return item;
    }
    return null;
  }

  List<Map<String, dynamic>> anchorsFor(String id) =>
      anchors.where((item) => item['node_id'] == id).toList();
  List<Map<String, dynamic>> related(String id) =>
      edges.where((item) => item['from'] == id || item['to'] == id).toList();
  List<Map<String, dynamic>> outgoing(String id) =>
      edges.where((item) => item['from'] == id).toList();
  List<Map<String, dynamic>> incoming(String id) =>
      edges.where((item) => item['to'] == id).toList();
  List<Map<String, dynamic>> explanationsFor(String id) =>
      explanations.where((item) => item['subject_node_id'] == id).toList();
  Map<String, dynamic>? anchor(String id) {
    for (final item in anchors) {
      if (item['id'] == id) return item;
    }
    return null;
  }

  Map<String, dynamic>? evidenceById(String id) {
    for (final item in evidence) {
      if (item['id'] == id) return item;
    }
    return null;
  }

  List<Map<String, dynamic>> hypothesesFor(String id) =>
      hypotheses.where((item) => item['subject_node_id'] == id).toList();
  List<Map<String, dynamic>> conceptsFor(String id) =>
      occurrences.where((item) => item['subject_node_id'] == id).toList();
  List<Map<String, dynamic>> timelineFor(String id) =>
      timelineEvents.where((item) => item['subject_node_id'] == id).toList()
        ..sort(
          (left, right) => (right['occurred_at'] as String? ?? '').compareTo(
            left['occurred_at'] as String? ?? '',
          ),
        );
  List<Map<String, dynamic>> diagramsFor(String id) => diagrams
      .where((item) => (item['node_ids'] as List? ?? []).contains(id))
      .toList();

  /// Select the domain-declared entry point before falling back to topology.
  /// Record order is an implementation detail and must never decide where an
  /// investigation starts.
  String? get initialNodeId {
    final declared =
        raw['journey']?['current_node_id'] as String? ??
        raw['journey']?['entry_node_id'] as String?;
    if (declared != null && node(declared) != null) return declared;
    for (final traversal in traversals) {
      final entry = traversal['entry_node_id'] as String?;
      if (entry != null && node(entry) != null) return entry;
    }
    final roots = nodes.where((candidate) {
      final id = candidate['id'] as String?;
      return id != null &&
          !edges.any((edge) {
            return edge['to'] == id &&
                (edge['disposition'] as String? ?? 'primary') == 'primary';
          });
    });
    return roots.firstOrNull?['id'] as String? ??
        nodes.firstOrNull?['id'] as String?;
  }

  /// Prefer an explicit domain traversal. Older Journeys have no logical-path
  /// record, so use a finite primary-parent chain as an honest fallback.
  List<String> logicalPathFor(String id) {
    for (final traversal in traversals) {
      final path = (traversal['node_ids'] as List? ?? const []).cast<String>();
      if (path.contains(id)) return path.take(path.indexOf(id) + 1).toList();
    }
    final result = <String>[id];
    final seen = <String>{id};
    var current = id;
    while (true) {
      final parent = edges.where((edge) {
        return edge['to'] == current &&
            (edge['disposition'] as String? ?? 'primary') == 'primary';
      }).firstOrNull;
      final parentId = parent?['from'] as String?;
      if (parentId == null || !seen.add(parentId)) break;
      result.insert(0, parentId);
      current = parentId;
    }
    return result;
  }

  static JourneyGraph decode(String source) =>
      JourneyGraph(jsonDecode(source) as Map<String, dynamic>);
}
