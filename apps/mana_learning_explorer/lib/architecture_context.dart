import 'journey_graph.dart';

enum ArchitectureContextStatus {
  unavailable,
  partial,
  mapped,
  inferred,
  ambiguous,
}

enum ArchitectureViewKind { components, sequence }

class DiagramViewState {
  DiagramViewState({
    this.kind = ArchitectureViewKind.components,
    this.followCurrent = true,
  });

  ArchitectureViewKind kind;
  bool followCurrent;
  String? focusedElementId;

  /// Route changes focus an element but own neither traversal history nor route.
  void focus(String? elementId) => focusedElementId = elementId;
}

class ArchitectureContextModel {
  const ArchitectureContextModel({
    required this.status,
    required this.diagrams,
    required this.component,
    required this.participant,
    required this.executionPath,
    required this.step,
    required this.depth,
    required this.transitionKind,
    required this.provenance,
    required this.focusedElementId,
  });

  final ArchitectureContextStatus status;
  final List<Map<String, dynamic>> diagrams;
  final String? component;
  final String? participant;
  final List<String> executionPath;
  final String? step;
  final int? depth;
  final String? transitionKind;
  final String? provenance;
  final String? focusedElementId;

  bool get isAsync => transitionKind == 'async' || transitionKind == 'event';
  bool get hasComponents =>
      diagrams.any((diagram) => diagram['kind'] == 'component');
  bool get hasSequence =>
      diagrams.any((diagram) => diagram['kind'] == 'sequence');

  String get statusMessage => switch (status) {
    ArchitectureContextStatus.unavailable =>
      'No architecture or execution context is mapped to this node.',
    ArchitectureContextStatus.partial =>
      'A diagram artifact is mapped, but component/call semantics are unavailable.',
    ArchitectureContextStatus.mapped => 'Analysis-backed architecture context.',
    ArchitectureContextStatus.inferred =>
      'Inferred architecture context — inspect provenance before relying on it.',
    ArchitectureContextStatus.ambiguous =>
      'Multiple context mappings are available; no call stack was selected.',
  };

  factory ArchitectureContextModel.build({
    required JourneyGraph graph,
    required String nodeId,
  }) {
    final diagrams = graph.diagramsFor(nodeId);
    if (diagrams.isEmpty) {
      return const ArchitectureContextModel(
        status: ArchitectureContextStatus.unavailable,
        diagrams: [],
        component: null,
        participant: null,
        executionPath: [],
        step: null,
        depth: null,
        transitionKind: null,
        provenance: null,
        focusedElementId: null,
      );
    }
    final bindings = <Map<String, dynamic>>[];
    for (final diagram in diagrams) {
      for (final raw in (diagram['elements'] as List? ?? const [])) {
        if (raw is Map<String, dynamic> &&
            ((raw['node_ids'] as List? ?? const []).contains(nodeId))) {
          bindings.add({...raw, '_diagram': diagram});
        }
      }
    }
    if (bindings.isEmpty) {
      return ArchitectureContextModel(
        status: ArchitectureContextStatus.partial,
        diagrams: diagrams,
        component: null,
        participant: null,
        executionPath: const [],
        step: null,
        depth: null,
        transitionKind: null,
        provenance: _journeyRevision(graph),
        focusedElementId: null,
      );
    }
    if (bindings.length > 1) {
      return ArchitectureContextModel(
        status: ArchitectureContextStatus.ambiguous,
        diagrams: diagrams,
        component: null,
        participant: null,
        executionPath: const [],
        step: null,
        depth: null,
        transitionKind: null,
        provenance: _journeyRevision(graph),
        focusedElementId: null,
      );
    }
    final binding = bindings.single;
    final diagram = binding['_diagram'] as Map<String, dynamic>;
    final context = binding['context'] as Map<String, dynamic>? ?? const {};
    final provenance =
        binding['provenance'] as Map<String, dynamic>? ??
        diagram['provenance'] as Map<String, dynamic>?;
    final inferred =
        provenance?['inferred'] == true ||
        provenance?['confidence'] == 'inferred';
    return ArchitectureContextModel(
      status: inferred
          ? ArchitectureContextStatus.inferred
          : ArchitectureContextStatus.mapped,
      diagrams: diagrams,
      component:
          context['component'] as String? ?? binding['component'] as String?,
      participant:
          context['participant'] as String? ??
          binding['participant'] as String?,
      executionPath: ((context['execution_path'] as List? ?? const [])
          .cast<String>()),
      step: context['step'] as String? ?? binding['step'] as String?,
      depth: context['depth'] as int? ?? binding['depth'] as int?,
      transitionKind:
          context['transition_kind'] as String? ??
          binding['transition_kind'] as String?,
      provenance:
          provenance?['snapshot'] as String? ??
          provenance?['revision'] as String? ??
          _journeyRevision(graph),
      focusedElementId: binding['id'] as String?,
    );
  }

  static String? _journeyRevision(JourneyGraph graph) =>
      graph.raw['journey']?['repository_revision'] as String?;
}
