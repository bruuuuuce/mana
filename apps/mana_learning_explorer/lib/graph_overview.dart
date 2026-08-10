import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'journey_graph.dart';

enum GraphRelationStyle { primary, alternative, deferred, related }

class GraphNodePosition {
  const GraphNodePosition(this.id, this.position);
  final String id;
  final Offset position;
}

class GraphRelation {
  const GraphRelation({
    required this.id,
    required this.from,
    required this.to,
    required this.kind,
    required this.style,
  });
  final String id;
  final String from;
  final String to;
  final String kind;
  final GraphRelationStyle style;
}

/// Finite, deterministic projection of Journey topology. It never unfolds
/// cycles: each domain node appears exactly once and every relation is a link.
class GraphOverviewModel {
  const GraphOverviewModel({
    required this.nodes,
    required this.relations,
    required this.positions,
  });
  final List<Map<String, dynamic>> nodes;
  final List<GraphRelation> relations;
  final Map<String, Offset> positions;

  factory GraphOverviewModel.build(JourneyGraph graph) {
    final nodes = graph.nodes.toList()
      ..sort((a, b) => '${a['id']}'.compareTo('${b['id']}'));
    final positions = <String, Offset>{};
    const columns = 4;
    for (var index = 0; index < nodes.length; index++) {
      positions[nodes[index]['id'] as String] = Offset(
        80 + (index % columns) * 250.0,
        80 + (index ~/ columns) * 150.0,
      );
    }
    final relations =
        graph.edges
            .where(
              (edge) =>
                  positions.containsKey(edge['from']) &&
                  positions.containsKey(edge['to']),
            )
            .map(
              (edge) => GraphRelation(
                id:
                    edge['id'] as String? ??
                    '${edge['from']}→${edge['to']}:${edge['kind']}',
                from: edge['from'] as String,
                to: edge['to'] as String,
                kind: edge['kind'] as String? ?? 'RELATED',
                style: _styleFor(edge),
              ),
            )
            .toList()
          ..sort((a, b) => a.id.compareTo(b.id));
    return GraphOverviewModel(
      nodes: nodes,
      relations: relations,
      positions: positions,
    );
  }

  static GraphRelationStyle _styleFor(Map<String, dynamic> edge) {
    final disposition = edge['disposition'] as String? ?? 'primary';
    if (disposition == 'deferred') return GraphRelationStyle.deferred;
    if (disposition == 'alternative' || edge['role'] == 'alternative') {
      return GraphRelationStyle.alternative;
    }
    if (edge['kind'] == 'RELATED_TO') return GraphRelationStyle.related;
    return GraphRelationStyle.primary;
  }
}

class JourneyGraphOverview extends StatefulWidget {
  const JourneyGraphOverview({
    super.key,
    required this.graph,
    required this.currentNodeId,
    required this.visitedNodeIds,
    required this.onNodeSelected,
    required this.onRelationSelected,
    this.centerRequest = 0,
  });
  final JourneyGraph graph;
  final String currentNodeId;
  final Set<String> visitedNodeIds;
  final ValueChanged<String> onNodeSelected;
  final ValueChanged<GraphRelation> onRelationSelected;
  final int centerRequest;

  @override
  State<JourneyGraphOverview> createState() => _JourneyGraphOverviewState();
}

class _JourneyGraphOverviewState extends State<JourneyGraphOverview> {
  final TransformationController _transform = TransformationController();
  late GraphOverviewModel _model;

  @override
  void initState() {
    super.initState();
    _model = GraphOverviewModel.build(widget.graph);
    WidgetsBinding.instance.addPostFrameCallback((_) => _centerOnCurrent());
  }

  @override
  void didUpdateWidget(covariant JourneyGraphOverview oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.graph != widget.graph) {
      _model = GraphOverviewModel.build(widget.graph);
    }
    if (oldWidget.currentNodeId != widget.currentNodeId ||
        oldWidget.centerRequest != widget.centerRequest) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _centerOnCurrent());
    }
  }

  @override
  void dispose() {
    _transform.dispose();
    super.dispose();
  }

  void _centerOnCurrent() {
    final point = _model.positions[widget.currentNodeId];
    if (point == null || !mounted) return;
    _transform.value = Matrix4.identity()
      ..setTranslationRaw(380 - point.dx, 280 - point.dy, 0);
  }

  @override
  Widget build(BuildContext context) {
    final nodeCount = _model.nodes.length;
    final rows = math.max(1, (nodeCount / 4).ceil());
    final canvasSize = Size(1200, math.max(620, rows * 150.0 + 120));
    return Column(
      children: [
        Material(
          color: Theme.of(context).colorScheme.surfaceContainerLow,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(
              children: [
                const Icon(Icons.account_tree_outlined),
                const SizedBox(width: 8),
                const Expanded(child: Text('GRAPH OVERVIEW')),
                const Text(
                  'Solid: primary  ·  dashed: alternative/deferred  ·  dotted: related',
                ),
                IconButton(
                  onPressed: _centerOnCurrent,
                  icon: const Icon(Icons.my_location),
                  tooltip: 'Center on current node (Ctrl+L)',
                ),
              ],
            ),
          ),
        ),
        Expanded(
          child: ClipRect(
            child: InteractiveViewer(
              transformationController: _transform,
              minScale: .45,
              maxScale: 2.5,
              constrained: false,
              child: SizedBox(
                width: canvasSize.width,
                height: canvasSize.height,
                child: Stack(
                  children: [
                    Positioned.fill(
                      child: _GraphEdges(
                        model: _model,
                        onSelected: widget.onRelationSelected,
                      ),
                    ),
                    ..._model.nodes.map((node) => _node(node)),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _node(Map<String, dynamic> node) {
    final id = node['id'] as String;
    final point = _model.positions[id]!;
    final current = id == widget.currentNodeId;
    final visited = widget.visitedNodeIds.contains(id);
    return Positioned(
      left: point.dx,
      top: point.dy,
      child: Semantics(
        button: true,
        selected: current,
        label:
            '${current ? 'Current ' : ''}${visited ? 'visited ' : ''}node ${node['label'] ?? id}',
        child: SizedBox(
          width: 190,
          child: Card(
            color: current
                ? Theme.of(context).colorScheme.primaryContainer
                : null,
            child: InkWell(
              onTap: () => widget.onNodeSelected(id),
              borderRadius: BorderRadius.circular(12),
              child: Padding(
                padding: const EdgeInsets.all(10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      current
                          ? 'CURRENT'
                          : visited
                          ? 'VISITED'
                          : 'NODE',
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                    Text(
                      '${node['label'] ?? id}',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      id,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _GraphEdges extends StatelessWidget {
  const _GraphEdges({required this.model, required this.onSelected});
  final GraphOverviewModel model;
  final ValueChanged<GraphRelation> onSelected;
  @override
  Widget build(BuildContext context) => GestureDetector(
    behavior: HitTestBehavior.translucent,
    onTapUp: (event) {
      GraphRelation? closest;
      var distance = double.infinity;
      for (final relation in model.relations) {
        final a = model.positions[relation.from]! + const Offset(95, 38);
        final b = model.positions[relation.to]! + const Offset(95, 38);
        final midpoint = Offset((a.dx + b.dx) / 2, (a.dy + b.dy) / 2);
        final next = (event.localPosition - midpoint).distance;
        if (next < distance) {
          distance = next;
          closest = relation;
        }
      }
      if (closest != null && distance < 32) onSelected(closest);
    },
    child: CustomPaint(
      painter: _GraphEdgePainter(model, Theme.of(context).colorScheme),
    ),
  );
}

class _GraphEdgePainter extends CustomPainter {
  const _GraphEdgePainter(this.model, this.colors);
  final GraphOverviewModel model;
  final ColorScheme colors;
  @override
  void paint(Canvas canvas, Size size) {
    for (final relation in model.relations) {
      final start = model.positions[relation.from]! + const Offset(190, 38);
      final end = model.positions[relation.to]! + const Offset(0, 38);
      final paint = Paint()
        ..color = _color(relation.style)
        ..strokeWidth = relation.style == GraphRelationStyle.primary
            ? 2.5
            : 1.7;
      final points = _segments(start, end, relation.style);
      for (final segment in points) {
        canvas.drawLine(segment.$1, segment.$2, paint);
      }
      final direction = (end - start);
      final unit = direction / math.max(1, direction.distance);
      final arrow = Path()
        ..moveTo(end.dx, end.dy)
        ..lineTo(
          end.dx - unit.dx * 10 - unit.dy * 5,
          end.dy - unit.dy * 10 + unit.dx * 5,
        )
        ..lineTo(
          end.dx - unit.dx * 10 + unit.dy * 5,
          end.dy - unit.dy * 10 - unit.dx * 5,
        )
        ..close();
      canvas.drawPath(arrow, paint);
    }
  }

  Color _color(GraphRelationStyle style) => switch (style) {
    GraphRelationStyle.primary => colors.primary,
    GraphRelationStyle.alternative => colors.tertiary,
    GraphRelationStyle.deferred => colors.outline,
    GraphRelationStyle.related => colors.secondary,
  };
  List<(Offset, Offset)> _segments(
    Offset start,
    Offset end,
    GraphRelationStyle style,
  ) {
    if (style == GraphRelationStyle.primary) return [(start, end)];
    final total = (end - start).distance;
    final unit = (end - start) / math.max(1, total);
    final dash = style == GraphRelationStyle.related ? 2.0 : 8.0;
    final gap = style == GraphRelationStyle.related ? 5.0 : 5.0;
    final result = <(Offset, Offset)>[];
    for (var offset = 0.0; offset < total; offset += dash + gap) {
      result.add((
        start + unit * offset,
        start + unit * math.min(offset + dash, total),
      ));
    }
    return result;
  }

  @override
  bool shouldRepaint(covariant _GraphEdgePainter old) =>
      old.model != model || old.colors != colors;
}
