import 'package:flutter_test/flutter_test.dart';
import 'package:mana_learning_explorer/explorer_navigation.dart';
import 'package:mana_learning_explorer/investigation_prompt.dart';
import 'package:mana_learning_explorer/journey_graph.dart';
import 'package:mana_learning_explorer/source_workspace.dart';

void main() {
  JourneyGraph graph() => JourneyGraph.decode(r'''
    {
      "journey":{"repository_revision":"journey-snapshot"},
      "nodes":[{"id":"root","label":"Entry"},{"id":"current","label":"Service \"edge\""},{"id":"next","label":"Worker"}],
      "traversals":[{"node_ids":["root","current"]}],
      "anchors":[
        {"id":"first","node_id":"current","revision":"abc123","path":"lib/service.dart","range":{"start_line":4,"end_line":8}},
        {"id":"second","node_id":"current","revision":"abc123","path":"test/service_test.dart","range":{"start_line":20,"end_line":25}}
      ],
      "evidence":[
        {"id":"support","kind":"source_range","anchor_id":"first","summary":"Supports `cache`\nwith a newline"},
        {"id":"contradiction","kind":"test","anchor_id":"second","summary":"A test disagrees"}
      ],
      "hypotheses":[{"id":"hyp","subject_node_id":"current","supports":["support"],"contradicts":["contradiction"]}],
      "edges":[{"id":"edge","from":"current","to":"next","kind":"CALLS","disposition":"primary"}],
      "diagrams":[{"id":"sequence","kind":"sequence","node_ids":["current"],"elements":[{"id":"message-1","kind":"message","node_ids":["current"],"context":{"component":"api","execution_path":["HTTP","Worker"],"transition_kind":"async"},"provenance":{"snapshot":"analysis-42"}}]}]
    }
  ''');

  test('builds an exact, deterministic source-backed handoff', () {
    final prompt = const InvestigationPromptBuilder().build(
      graph: graph(),
      route: const ExplorerRoute(
        journeyId: 'journey-1',
        nodeId: 'current',
        evidenceId: 'support',
        sourceLocation: SourceLocation(
          projectRoot: '/project',
          path: 'lib/service.dart',
          startLine: 4,
          endLine: 8,
          revision: 'abc123',
        ),
      ),
      projectRoot: '/project',
      requestedGoal: 'Check "cache" behavior\nwithout guessing.',
      selectedDiagramElementId: 'message-1',
    );

    expect(
      prompt,
      contains('"Check \\"cache\\" behavior\\nwithout guessing."'),
    );
    expect(prompt, contains('"lib/service.dart:4-8" · revision "abc123"'));
    expect(
      prompt,
      contains('"test/service_test.dart:20-25" · revision "abc123"'),
    );
    expect(prompt, contains('"Supports hypothesis"'));
    expect(prompt, contains('"Contradicts hypothesis"'));
    expect(
      prompt,
      contains('Selected diagram element: "message-1" · "message"'),
    );
    expect(prompt, contains('asynchronous/event boundary'));
  });

  test('does not claim unavailable source content or missing context', () {
    final empty = JourneyGraph.decode('''{"nodes":[{"id":"node"}]}''');
    final prompt = const InvestigationPromptBuilder().build(
      graph: empty,
      route: const ExplorerRoute(journeyId: 'journey', nodeId: 'node'),
      projectRoot: '/project',
      requestedGoal: '',
      displayedSource: const ResolvedSource(
        location: SourceLocation(
          projectRoot: '/project',
          path: 'missing.dart',
          startLine: 1,
          endLine: 1,
        ),
        state: SourceState.missing,
      ),
    );

    expect(prompt, contains('No source reference is recorded'));
    expect(prompt, contains('No evidence is linked'));
    expect(
      prompt,
      contains('Continue investigating the current journey context.'),
    );
    expect(prompt, contains('Do not assume source text is available'));
  });
}
