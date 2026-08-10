import 'dart:convert';

class JourneyGraph {
  JourneyGraph(this.raw);
  final Map<String, dynamic> raw;

  String get title => raw['journey']?['title'] as String? ?? 'Untitled Journey';
  List<Map<String, dynamic>> get nodes => _records('nodes');
  List<Map<String, dynamic>> get edges => _records('edges');
  List<Map<String, dynamic>> get anchors => _records('anchors');
  List<Map<String, dynamic>> get explanations => _records('explanations');
  List<Map<String, dynamic>> get occurrences => _records('concept_occurrences');
  List<Map<String, dynamic>> get timelineEvents => _records('timeline_events');
  List<Map<String, dynamic>> get diagrams => _records('diagrams');

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
  List<Map<String, dynamic>> explanationsFor(String id) =>
      explanations.where((item) => item['subject_node_id'] == id).toList();
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

  static JourneyGraph decode(String source) =>
      JourneyGraph(jsonDecode(source) as Map<String, dynamic>);
}
