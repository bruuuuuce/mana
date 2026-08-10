import 'journey_graph.dart';
import 'journey_navigator.dart';
import 'source_workspace.dart';

class InspectorEvidence {
  const InspectorEvidence({
    required this.evidence,
    required this.location,
    required this.relationship,
  });

  final Map<String, dynamic> evidence;
  final SourceLocation? location;
  final String? relationship;

  String get id => evidence['id'] as String;
  String get kind => evidence['kind'] as String? ?? 'evidence';
  String get summary =>
      evidence['summary'] as String? ?? 'No summary provided.';
}

class InspectorRelation {
  const InspectorRelation({
    required this.edge,
    required this.target,
    required this.group,
    required this.incoming,
  });

  final Map<String, dynamic> edge;
  final Map<String, dynamic> target;
  final JourneyPathRole group;
  final bool incoming;

  String get targetId => target['id'] as String;
  String get label => target['label'] as String? ?? targetId;
  String get kind => edge['kind'] as String? ?? 'RELATED';
}

class InvestigationInspectorModel {
  InvestigationInspectorModel({
    required this.explanations,
    required this.hypotheses,
    required this.evidence,
    required this.primary,
    required this.alternatives,
    required this.deferred,
    required this.related,
    required this.cameFrom,
    required this.isTerminal,
  });

  final List<Map<String, dynamic>> explanations;
  final List<Map<String, dynamic>> hypotheses;
  final List<InspectorEvidence> evidence;
  final List<InspectorRelation> primary;
  final List<InspectorRelation> alternatives;
  final List<InspectorRelation> deferred;
  final List<InspectorRelation> related;
  final List<InspectorRelation> cameFrom;
  final bool isTerminal;

  factory InvestigationInspectorModel.build({
    required JourneyGraph graph,
    required String nodeId,
    required String projectRoot,
  }) {
    final explanations = graph.explanationsFor(nodeId);
    final hypotheses = graph.hypothesesFor(nodeId);
    final evidenceIds = <String>{
      for (final anchor in graph.anchorsFor(nodeId))
        ...graph.evidence
            .where((item) => item['anchor_id'] == anchor['id'])
            .map((item) => item['id'] as String),
      for (final explanation in explanations)
        ...((explanation['evidence_ids'] as List? ?? const []).cast<String>()),
      for (final hypothesis in hypotheses) ...[
        ...((hypothesis['supports'] as List? ?? const []).cast<String>()),
        ...((hypothesis['contradicts'] as List? ?? const []).cast<String>()),
      ],
    };
    final evidence = evidenceIds
        .map(graph.evidenceById)
        .whereType<Map<String, dynamic>>()
        .map((item) {
          final anchorId = item['anchor_id'] as String?;
          final anchor = anchorId == null ? null : graph.anchor(anchorId);
          final relationship =
              hypotheses.any(
                (hypothesis) => (hypothesis['supports'] as List? ?? const [])
                    .contains(item['id']),
              )
              ? 'Supports hypothesis'
              : hypotheses.any(
                  (hypothesis) =>
                      (hypothesis['contradicts'] as List? ?? const []).contains(
                        item['id'],
                      ),
                )
              ? 'Contradicts hypothesis'
              : null;
          return InspectorEvidence(
            evidence: item,
            location: anchor == null
                ? null
                : SourceLocation.fromAnchor(projectRoot, anchor),
            relationship: relationship,
          );
        })
        .toList();

    final primary = <InspectorRelation>[];
    final alternatives = <InspectorRelation>[];
    final deferred = <InspectorRelation>[];
    final related = <InspectorRelation>[];
    for (final edge in graph.outgoing(nodeId)) {
      final target = graph.node(edge['to'] as String? ?? '');
      if (target == null) continue;
      final relation = InspectorRelation(
        edge: edge,
        target: target,
        group: _roleFor(edge),
        incoming: false,
      );
      switch (relation.group) {
        case JourneyPathRole.primary:
          primary.add(relation);
        case JourneyPathRole.alternative:
          alternatives.add(relation);
        case JourneyPathRole.deferred:
          deferred.add(relation);
        case JourneyPathRole.related:
          related.add(relation);
      }
    }
    final cameFrom = graph.incoming(nodeId).map((edge) {
      final target = graph.node(edge['from'] as String? ?? '')!;
      return InspectorRelation(
        edge: edge,
        target: target,
        group: _roleFor(edge),
        incoming: true,
      );
    }).toList();
    return InvestigationInspectorModel(
      explanations: explanations,
      hypotheses: hypotheses,
      evidence: evidence,
      primary: primary,
      alternatives: alternatives,
      deferred: deferred,
      related: related,
      cameFrom: cameFrom,
      isTerminal: graph.outgoing(nodeId).isEmpty,
    );
  }

  static JourneyPathRole _roleFor(Map<String, dynamic> edge) {
    final disposition = edge['disposition'] as String? ?? 'primary';
    if (disposition == 'deferred') return JourneyPathRole.deferred;
    if (disposition == 'alternative' || edge['role'] == 'alternative') {
      return JourneyPathRole.alternative;
    }
    if (edge['kind'] == 'RELATED_TO') return JourneyPathRole.related;
    return JourneyPathRole.primary;
  }
}
