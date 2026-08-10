import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'architecture_context.dart';
import 'diagram_detachment.dart';
import 'explorer_navigation.dart';
import 'journey_graph.dart';

enum DiagramScope { currentPath, currentBranch, wholeStream }

class _PreviousMappedStepIntent extends Intent {
  const _PreviousMappedStepIntent();
}

class _NextMappedStepIntent extends Intent {
  const _NextMappedStepIntent();
}

class _LocateCurrentIntent extends Intent {
  const _LocateCurrentIntent();
}

class DiagramElementBinding {
  const DiagramElementBinding({
    required this.elementId,
    this.nodeIds = const [],
    this.relationIds = const [],
    this.semanticRole = 'context',
  });
  final String elementId;
  final List<String> nodeIds;
  final List<String> relationIds;
  final String semanticRole;
}

class DiagramDocument {
  const DiagramDocument({
    required this.id,
    required this.kind,
    required this.elements,
    required this.relations,
    required this.provenance,
  });
  final String id;
  final String kind;
  final List<DiagramElementBinding> elements;
  final List<DiagramElementBinding> relations;
  final String? provenance;

  factory DiagramDocument.fromJourney({
    required JourneyGraph graph,
    required Map<String, dynamic> diagram,
    required DiagramScope scope,
    required String currentNodeId,
  }) {
    final all = (diagram['node_ids'] as List? ?? const []).cast<String>();
    final allowed = switch (scope) {
      DiagramScope.wholeStream => all.toSet(),
      DiagramScope.currentPath => graph.logicalPathFor(currentNodeId).toSet(),
      DiagramScope.currentBranch => {
        currentNodeId,
        ...graph.outgoing(currentNodeId).map((edge) => edge['to'] as String),
        ...graph.incoming(currentNodeId).map((edge) => edge['from'] as String),
      },
    }.intersection(all.toSet());
    final persistedElements = (diagram['elements'] as List? ?? const [])
        .whereType<Map<String, dynamic>>()
        .toList();
    final elements = persistedElements.isEmpty
        ? allowed
              .map(
                (id) => DiagramElementBinding(
                  elementId: 'node:$id',
                  nodeIds: [id],
                  semanticRole: diagram['kind'] == 'sequence'
                      ? 'participant'
                      : 'component',
                ),
              )
              .toList()
        : persistedElements
              .map(
                (element) => DiagramElementBinding(
                  elementId: element['id'] as String,
                  nodeIds: ((element['node_ids'] as List? ?? const [])
                      .cast<String>()
                      .where(allowed.contains)
                      .toList()),
                  relationIds: (element['relation_ids'] as List? ?? const [])
                      .cast<String>(),
                  semanticRole: element['role'] as String? ?? 'context',
                ),
              )
              .toList();
    final relations = graph.edges
        .where(
          (edge) =>
              allowed.contains(edge['from']) && allowed.contains(edge['to']),
        )
        .map(
          (edge) => DiagramElementBinding(
            elementId: 'edge:${edge['id']}',
            nodeIds: [edge['to'] as String],
            relationIds: [edge['id'] as String],
            semanticRole: edge['kind'] as String? ?? 'relation',
          ),
        )
        .toList();
    return DiagramDocument(
      id: diagram['id'] as String? ?? 'derived-diagram',
      kind: diagram['kind'] as String? ?? 'component',
      elements: elements,
      relations: relations,
      provenance:
          (diagram['provenance'] as Map?)?['snapshot'] as String? ??
          graph.raw['journey']?['repository_revision'] as String?,
    );
  }
}

class DiagramWorkspace extends StatefulWidget {
  const DiagramWorkspace({
    super.key,
    required this.graph,
    required this.diagrams,
    required this.currentRoute,
    required this.onNavigate,
    this.detachment = DiagramDetachmentCapability.unavailable,
    required this.windowState,
  });
  final JourneyGraph graph;
  final List<Map<String, dynamic>> diagrams;
  final ValueListenable<ExplorerRoute?> currentRoute;
  final ValueChanged<ExplorerRoute> onNavigate;
  final DiagramDetachmentCapability detachment;
  final DiagramWindowState windowState;

  @override
  State<DiagramWorkspace> createState() => _DiagramWorkspaceState();
}

class _DiagramWorkspaceState extends State<DiagramWorkspace> {
  final _transform = TransformationController();
  DiagramScope _scope = DiagramScope.currentPath;
  bool _followCurrent = true;
  String? _selectedElement;
  late ArchitectureViewKind _kind;

  @override
  void initState() {
    super.initState();
    widget.currentRoute.addListener(_onRouteChanged);
    _kind = widget.diagrams.any((d) => d['kind'] == 'component')
        ? ArchitectureViewKind.components
        : ArchitectureViewKind.sequence;
  }

  @override
  void dispose() {
    widget.currentRoute.removeListener(_onRouteChanged);
    _transform.dispose();
    super.dispose();
  }

  void _onRouteChanged() {
    if (_followCurrent) _transform.value = Matrix4.identity();
  }

  @override
  Widget build(BuildContext context) => ValueListenableBuilder<ExplorerRoute?>(
    valueListenable: widget.currentRoute,
    builder: (context, route, _) {
      if (route == null) return const SizedBox.shrink();
      final diagram = widget.diagrams.firstWhere(
        (item) =>
            item['kind'] == _kind.name.replaceFirst('components', 'component'),
        orElse: () => widget.diagrams.first,
      );
      final document = DiagramDocument.fromJourney(
        graph: widget.graph,
        diagram: diagram,
        scope: _scope,
        currentNodeId: route.nodeId,
      );
      return Shortcuts(
        shortcuts: const {
          SingleActivator(LogicalKeyboardKey.arrowLeft, alt: true):
              _PreviousMappedStepIntent(),
          SingleActivator(LogicalKeyboardKey.arrowRight, alt: true):
              _NextMappedStepIntent(),
          SingleActivator(LogicalKeyboardKey.keyL, control: true):
              _LocateCurrentIntent(),
        },
        child: Actions(
          actions: {
            _PreviousMappedStepIntent:
                CallbackAction<_PreviousMappedStepIntent>(
                  onInvoke: (_) => _step(-1, document),
                ),
            _NextMappedStepIntent: CallbackAction<_NextMappedStepIntent>(
              onInvoke: (_) => _step(1, document),
            ),
            _LocateCurrentIntent: CallbackAction<_LocateCurrentIntent>(
              onInvoke: (_) => _locateCurrent(),
            ),
          },
          child: Focus(
            autofocus: true,
            child: Column(
              children: [
                _toolbar(document),
                Expanded(
                  child: InteractiveViewer(
                    transformationController: _transform,
                    minScale: .4,
                    maxScale: 3,
                    child: Center(child: _diagram(document, route)),
                  ),
                ),
                if (_selectedElement != null)
                  Padding(
                    padding: const EdgeInsets.all(8),
                    child: Text('Selected element: $_selectedElement'),
                  ),
              ],
            ),
          ),
        ),
      );
    },
  );

  Widget _toolbar(DiagramDocument document) => Wrap(
    spacing: 8,
    runSpacing: 4,
    alignment: WrapAlignment.center,
    children: [
      SegmentedButton<ArchitectureViewKind>(
        segments: const [
          ButtonSegment(
            value: ArchitectureViewKind.components,
            label: Text('Components'),
          ),
          ButtonSegment(
            value: ArchitectureViewKind.sequence,
            label: Text('Sequence'),
          ),
        ],
        selected: {_kind},
        onSelectionChanged: (value) => setState(() => _kind = value.single),
      ),
      DropdownButton<DiagramScope>(
        value: _scope,
        items: const [
          DropdownMenuItem(
            value: DiagramScope.currentPath,
            child: Text('Current path'),
          ),
          DropdownMenuItem(
            value: DiagramScope.currentBranch,
            child: Text('Current branch'),
          ),
          DropdownMenuItem(
            value: DiagramScope.wholeStream,
            child: Text('Whole stream'),
          ),
        ],
        onChanged: (value) => setState(() => _scope = value!),
      ),
      IconButton(
        onPressed: () => _zoom(1.2),
        icon: const Icon(Icons.zoom_in),
        tooltip: 'Zoom in',
      ),
      IconButton(
        onPressed: () => _zoom(.8),
        icon: const Icon(Icons.zoom_out),
        tooltip: 'Zoom out',
      ),
      IconButton(
        onPressed: () => _transform.value = Matrix4.identity(),
        icon: const Icon(Icons.fit_screen),
        tooltip: 'Fit to view',
      ),
      IconButton(
        onPressed: _locateCurrent,
        icon: const Icon(Icons.my_location),
        tooltip: 'Locate current (Ctrl+L)',
      ),
      IconButton(
        onPressed: () => _transform.value = Matrix4.identity(),
        icon: const Icon(Icons.aspect_ratio),
        tooltip: 'Actual size',
      ),
      IconButton(
        onPressed: () => _step(-1, document),
        icon: const Icon(Icons.skip_previous),
        tooltip: 'Previous mapped step (Alt+Left)',
      ),
      IconButton(
        onPressed: () => _step(1, document),
        icon: const Icon(Icons.skip_next),
        tooltip: 'Next mapped step (Alt+Right)',
      ),
      FilterChip(
        label: const Text('Follow current'),
        selected: _followCurrent,
        onSelected: (value) => setState(() => _followCurrent = value),
      ),
      OutlinedButton.icon(
        onPressed: _requestDetach,
        icon: const Icon(Icons.open_in_new),
        label: const Text('Detach'),
      ),
      Text(
        document.provenance == null
            ? 'No snapshot provenance'
            : 'Snapshot ${document.provenance}',
      ),
    ],
  );

  void _requestDetach() {
    if (widget.windowState.requestDetach(widget.detachment)) return;
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Detached window unavailable'),
        content: Text(
          '${widget.detachment.reason}\n\nThis workspace remains in the application window and shares the Explorer\'s single route and history.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  void _zoom(double scale) =>
      _transform.value = _transform.value.clone()
        ..scaleByDouble(scale, scale, scale, 1);

  void _locateCurrent() => _transform.value = Matrix4.identity();

  void _step(int delta, DiagramDocument document) {
    final route = widget.currentRoute.value;
    if (route == null) return;
    final mapped = document.elements
        .expand((element) => element.nodeIds)
        .toSet();
    final path = widget.graph
        .logicalPathFor(route.nodeId)
        .where(mapped.contains)
        .toList();
    final index = path.indexOf(route.nodeId);
    final next = index + delta;
    if (next < 0 || next >= path.length) return;
    widget.onNavigate(
      ExplorerRoute(journeyId: route.journeyId, nodeId: path[next]),
    );
  }

  Widget _diagram(DiagramDocument document, ExplorerRoute route) => SizedBox(
    width: 900,
    child: Card(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '${document.kind.toUpperCase()} • ${document.id}',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 20),
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: document.elements
                  .map((element) => _element(element, route))
                  .toList(),
            ),
            const SizedBox(height: 20),
            ...document.relations.map(_relation),
          ],
        ),
      ),
    ),
  );

  Widget _element(DiagramElementBinding binding, ExplorerRoute route) {
    final id = binding.nodeIds.singleOrNull;
    final node = id == null ? null : widget.graph.node(id);
    final current = id == route.nodeId;
    final label = node?['label'] as String? ?? binding.elementId;
    return Semantics(
      button: true,
      selected: current,
      label: '$label, ${binding.semanticRole}${current ? ', current' : ''}',
      hint: binding.nodeIds.isEmpty
          ? 'Diagram metadata only'
          : binding.nodeIds.length == 1
          ? 'Open mapped Journey node'
          : 'Choose a mapped Journey node',
      child: Tooltip(
        message: binding.nodeIds.isEmpty
            ? '$label: no mapped Journey node'
            : 'Open $label',
        child: FocusableActionDetector(
          onFocusChange: (focused) {
            if (focused) setState(() => _selectedElement = binding.elementId);
          },
          child: InkWell(
            borderRadius: BorderRadius.circular(18),
            onTap: () => _activate(binding),
            child: Chip(
              avatar: Icon(
                current
                    ? Icons.my_location
                    : binding.semanticRole == 'participant'
                    ? Icons.person_outline
                    : Icons.widgets_outlined,
              ),
              label: Text('$label${current ? ' • CURRENT' : ''}'),
              side: current
                  ? BorderSide(
                      color: Theme.of(context).colorScheme.primary,
                      width: 2,
                    )
                  : null,
              backgroundColor: current
                  ? Theme.of(context).colorScheme.primaryContainer
                  : null,
            ),
          ),
        ),
      ),
    );
  }

  Widget _relation(DiagramElementBinding binding) {
    final edgeId = binding.relationIds.singleOrNull;
    final edge = edgeId == null
        ? null
        : widget.graph.edges.where((e) => e['id'] == edgeId).firstOrNull;
    final kind = edge?['kind'] as String? ?? binding.semanticRole;
    return Semantics(
      button: true,
      label: '$kind relation, ${edge?['from'] ?? '?'} to ${edge?['to'] ?? '?'}',
      child: ListTile(
        leading: Icon(
          (edge?['kind'] == 'LOOP_BACK') ? Icons.loop : Icons.arrow_forward,
        ),
        title: Text(kind),
        subtitle: Text('${edge?['from'] ?? '?'} → ${edge?['to'] ?? '?'}'),
        onTap: () => _activate(binding),
      ),
    );
  }

  void _activate(DiagramElementBinding binding) {
    setState(() => _selectedElement = binding.elementId);
    if (binding.nodeIds.length == 1) {
      final current = widget.currentRoute.value!;
      widget.onNavigate(
        ExplorerRoute(
          journeyId: current.journeyId,
          nodeId: binding.nodeIds.single,
        ),
      );
      return;
    }
    if (binding.nodeIds.length > 1) {
      showModalBottomSheet<void>(
        context: context,
        builder: (context) => ListView(
          children: binding.nodeIds
              .map(
                (id) => ListTile(
                  title: Text(widget.graph.node(id)?['label'] as String? ?? id),
                  onTap: () {
                    Navigator.pop(context);
                    final current = widget.currentRoute.value!;
                    widget.onNavigate(
                      ExplorerRoute(journeyId: current.journeyId, nodeId: id),
                    );
                  },
                ),
              )
              .toList(),
        ),
      );
    }
  }
}
