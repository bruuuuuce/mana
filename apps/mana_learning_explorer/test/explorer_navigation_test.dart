import 'package:flutter_test/flutter_test.dart';
import 'package:mana_learning_explorer/explorer_navigation.dart';
import 'package:mana_learning_explorer/source_workspace.dart';

void main() {
  const a = ExplorerRoute(journeyId: 'journey-a', nodeId: 'node-a');
  const b = ExplorerRoute(journeyId: 'journey-a', nodeId: 'node-b');
  const c = ExplorerRoute(journeyId: 'journey-a', nodeId: 'node-c');

  test('replays node and evidence focus through Back and Forward', () {
    final state = TraversalState()..reset(a);
    final focused = b.copyWith(
      evidenceId: 'evidence-b',
      sourceLocation: const SourceLocation(
        projectRoot: '/project',
        path: 'lib/service.dart',
        startLine: 12,
        endLine: 18,
        revision: 'abc1234',
      ),
    );
    state.navigate(focused);
    state.navigate(c);

    expect(state.back(), focused);
    expect(state.back(), a);
    expect(state.forward(), focused);
    expect(state.forward(), c);
    expect(state.visitedNodeIds, {'node-a', 'node-b', 'node-c'});
  });

  test('cycles are stored as finite human traversal history', () {
    final state = TraversalState()..reset(a);
    state.navigate(b);
    state.navigate(
      a,
    ); // a graph LOOP_BACK must not recursively expand UI state.

    expect(state.current, a);
    expect(state.backStack, [a, b]);
    expect(state.back(), b);
    expect(state.back(), a);
    expect(state.canGoBack, isFalse);
  });

  test('a new journey resets incompatible history and visited nodes', () {
    final state = TraversalState()..reset(a);
    state.navigate(b);
    state.reset(const ExplorerRoute(journeyId: 'journey-b', nodeId: 'node-x'));

    expect(state.current?.journeyId, 'journey-b');
    expect(state.canGoBack, isFalse);
    expect(state.canGoForward, isFalse);
    expect(state.visitedNodeIds, {'node-x'});
  });
}
