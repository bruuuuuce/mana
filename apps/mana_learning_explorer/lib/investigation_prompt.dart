import 'dart:convert';

import 'architecture_context.dart';
import 'explorer_navigation.dart';
import 'investigation_inspector.dart';
import 'journey_graph.dart';
import 'source_workspace.dart';

/// A local, deterministic handoff payload. It intentionally contains only
/// analysis records and source identities, never guessed source contents.
class InvestigationPromptBuilder {
  const InvestigationPromptBuilder();

  String build({
    required JourneyGraph graph,
    required ExplorerRoute route,
    required String projectRoot,
    required String requestedGoal,
    ResolvedSource? displayedSource,
    String? selectedDiagramElementId,
  }) {
    final node = graph.node(route.nodeId);
    final inspector = InvestigationInspectorModel.build(
      graph: graph,
      nodeId: route.nodeId,
      projectRoot: projectRoot,
    );
    final architecture = ArchitectureContextModel.build(
      graph: graph,
      nodeId: route.nodeId,
    );
    final locations = <SourceLocation>{
      if (route.sourceLocation != null) route.sourceLocation!,
      ...graph
          .anchorsFor(route.nodeId)
          .map((anchor) => SourceLocation.fromAnchor(projectRoot, anchor)),
      ...inspector.evidence
          .map((evidence) => evidence.location)
          .whereType<SourceLocation>(),
    }.toList()..sort((a, b) => a.reference.compareTo(b.reference));
    final path = graph.logicalPathFor(route.nodeId);
    final related = graph.related(route.nodeId).toList()
      ..sort((a, b) => '${a['id']}'.compareTo('${b['id']}'));
    final selectedElement = _diagramElement(graph, selectedDiagramElementId);

    final lines = <String>[
      '# MANA investigation handoff',
      '',
      '## Requested investigation goal',
      _value(
        requestedGoal.trim().isEmpty
            ? 'Continue investigating the current journey context.'
            : requestedGoal.trim(),
      ),
      '',
      '## Current route',
      '- Journey: ${_value(route.journeyId)}',
      '- Node: ${_value(route.nodeId)}${node == null ? ' (record unavailable)' : ' — ${_value(node['label'] ?? route.nodeId)}'}',
      if (route.evidenceId != null)
        '- Selected evidence: ${_value(route.evidenceId)}',
      '',
      '## Source references',
      if (locations.isEmpty)
        '- No source reference is recorded for this route.'
      else
        ...locations.map((location) => _sourceLine(location, displayedSource)),
      '',
      '## Evidence',
      if (inspector.evidence.isEmpty)
        '- No evidence is linked to this node.'
      else
        ...inspector.evidence.map(
          (evidence) =>
              '- ${_value(evidence.id)} · ${_value(evidence.kind)}${evidence.relationship == null ? '' : ' · ${_value(evidence.relationship)}'}: ${_value(evidence.summary)}${evidence.location == null ? ' (no resolvable source range)' : ' @ ${_sourceIdentity(evidence.location!)}'}',
        ),
      '',
      '## Journey path and relations',
      '- Logical path: ${path.isEmpty ? 'No logical path is recorded.' : path.map((id) => _nodeIdentity(graph, id)).join(' → ')}',
      if (related.isEmpty)
        '- No related graph relations are recorded.'
      else
        ...related.map((edge) => '- ${_relationIdentity(graph, edge)}'),
      '',
      '## Architecture / execution context',
      '- Status: ${_value(architecture.status.name)}',
      if (architecture.component != null)
        '- Component: ${_value(architecture.component)}',
      if (architecture.participant != null)
        '- Participant: ${_value(architecture.participant)}',
      if (architecture.executionPath.isNotEmpty)
        '- Execution path: ${architecture.executionPath.map(_value).join(' → ')}',
      if (architecture.step != null) '- Step: ${_value(architecture.step)}',
      if (architecture.depth != null) '- Depth: ${architecture.depth}',
      if (architecture.transitionKind != null)
        '- Transition: ${_value(architecture.transitionKind)}${architecture.isAsync ? ' (asynchronous/event boundary)' : ''}',
      if (architecture.provenance != null)
        '- Analysis snapshot: ${_value(architecture.provenance)}',
      if (selectedElement == null && selectedDiagramElementId != null)
        '- Selected diagram element: ${_value(selectedDiagramElementId)} (details unavailable)',
      if (selectedElement != null)
        '- Selected diagram element: ${_value(selectedElement['id'])}${selectedElement['kind'] == null ? '' : ' · ${_value(selectedElement['kind'])}'}',
      '',
      '## Handoff constraints',
      '- Treat source references and snapshot metadata as authoritative identities.',
      '- Do not assume source text is available unless it is retrieved from the listed reference.',
      '- Distinguish evidence that supports a hypothesis from evidence that contradicts it.',
    ];
    return lines.join('\n');
  }

  String _sourceLine(SourceLocation location, ResolvedSource? displayed) {
    final state = displayed?.location == location ? displayed?.state : null;
    final availability = switch (state) {
      SourceState.snapshot =>
        displayed!.drifted
            ? 'analyzed snapshot; working tree differs'
            : 'analyzed snapshot',
      SourceState.workingTree => 'working tree; no snapshot identity',
      SourceState.snapshotUnavailable =>
        'snapshot unavailable; working tree is not authoritative',
      SourceState.missing => 'source unavailable',
      null => 'source availability not checked in this view',
    };
    return '- ${_sourceIdentity(location)} · $availability';
  }

  String _sourceIdentity(SourceLocation location) =>
      '${_value(location.reference)}${location.revision == null ? '' : ' · revision ${_value(location.revision)}'}${location.contentHash == null ? '' : ' · content hash ${_value(location.contentHash)}'}';

  String _nodeIdentity(JourneyGraph graph, String id) {
    final node = graph.node(id);
    return node == null
        ? _value(id)
        : '${_value(id)} (${_value(node['label'] ?? id)})';
  }

  String _relationIdentity(JourneyGraph graph, Map<String, dynamic> edge) =>
      '${_value(edge['id'] ?? 'relation')} · ${_value(edge['kind'] ?? 'RELATED')} · ${_nodeIdentity(graph, '${edge['from']}')} → ${_nodeIdentity(graph, '${edge['to']}')}';

  Map<String, dynamic>? _diagramElement(JourneyGraph graph, String? id) {
    if (id == null) return null;
    for (final diagram in graph.diagrams) {
      for (final element in (diagram['elements'] as List? ?? const [])) {
        if (element is Map<String, dynamic> && element['id'] == id) {
          return element;
        }
      }
    }
    return null;
  }

  /// JSON string syntax makes untrusted journey text unambiguous and preserves
  /// newlines, quotes, backticks, and other characters without Markdown escape
  /// rules leaking into the prompt structure.
  static String _value(Object? value) => jsonEncode(value?.toString() ?? '');
}
