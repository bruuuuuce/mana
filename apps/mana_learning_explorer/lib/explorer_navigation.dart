import 'source_workspace.dart';

/// A route is the single cross-panel selection contract for the Explorer.
/// Evidence/source focus may change without changing the selected node.
class ExplorerRoute {
  const ExplorerRoute({
    required this.journeyId,
    required this.nodeId,
    this.evidenceId,
    this.sourceLocation,
  });

  final String journeyId;
  final String nodeId;
  final String? evidenceId;
  final SourceLocation? sourceLocation;

  ExplorerRoute copyWith({
    String? evidenceId,
    SourceLocation? sourceLocation,
    bool clearEvidence = false,
    bool clearSourceLocation = false,
  }) => ExplorerRoute(
    journeyId: journeyId,
    nodeId: nodeId,
    evidenceId: clearEvidence ? null : evidenceId ?? this.evidenceId,
    sourceLocation: clearSourceLocation
        ? null
        : sourceLocation ?? this.sourceLocation,
  );

  @override
  bool operator ==(Object other) =>
      other is ExplorerRoute &&
      journeyId == other.journeyId &&
      nodeId == other.nodeId &&
      evidenceId == other.evidenceId &&
      sourceLocation == other.sourceLocation;

  @override
  int get hashCode =>
      Object.hash(journeyId, nodeId, evidenceId, sourceLocation);
}

/// UI traversal history is deliberately independent from Journey topology.
/// It is cycle-safe because it stores clicked routes, never expanded graph paths.
class TraversalState {
  ExplorerRoute? _current;
  final List<ExplorerRoute> _back = [];
  final List<ExplorerRoute> _forward = [];
  final Set<String> _visitedNodeIds = {};

  ExplorerRoute? get current => _current;
  List<ExplorerRoute> get backStack => List.unmodifiable(_back);
  List<ExplorerRoute> get forwardStack => List.unmodifiable(_forward);
  Set<String> get visitedNodeIds => Set.unmodifiable(_visitedNodeIds);
  bool get canGoBack => _back.isNotEmpty;
  bool get canGoForward => _forward.isNotEmpty;

  void reset(ExplorerRoute route) {
    _current = route;
    _back.clear();
    _forward.clear();
    _visitedNodeIds
      ..clear()
      ..add(route.nodeId);
  }

  bool navigate(ExplorerRoute route) {
    if (_current == route) return false;
    if (_current != null) _back.add(_current!);
    _current = route;
    _forward.clear();
    _visitedNodeIds.add(route.nodeId);
    return true;
  }

  ExplorerRoute? back() {
    if (_back.isEmpty || _current == null) return null;
    _forward.add(_current!);
    _current = _back.removeLast();
    _visitedNodeIds.add(_current!.nodeId);
    return _current;
  }

  ExplorerRoute? forward() {
    if (_forward.isEmpty || _current == null) return null;
    _back.add(_current!);
    _current = _forward.removeLast();
    _visitedNodeIds.add(_current!.nodeId);
    return _current;
  }
}
