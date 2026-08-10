import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';

import 'journey_graph.dart';

void main(List<String> args) =>
    runApp(ManaExplorerApp(config: ExplorerConfig.parse(args)));

class ExplorerConfig {
  const ExplorerConfig({
    required this.projectRoot,
    required this.manaRoot,
    this.journeyId,
  });
  final String projectRoot;
  final String manaRoot;
  final String? journeyId;

  factory ExplorerConfig.parse(List<String> args) {
    String value(String flag, String fallback) {
      final index = args.indexOf(flag);
      return index >= 0 && index + 1 < args.length ? args[index + 1] : fallback;
    }

    String? ancestorWith(Directory start, String child) {
      var directory = start;
      while (true) {
        if (Directory('${directory.path}/$child').existsSync()) {
          return directory.path;
        }
        final parent = directory.parent;
        if (parent.path == directory.path) return null;
        directory = parent;
      }
    }

    final starts = [
      Directory.current,
      File(Platform.resolvedExecutable).parent,
    ];
    String detect(String child) {
      for (final start in starts) {
        final found = ancestorWith(start, child);
        if (found != null) return found;
      }
      return Directory.current.path;
    }

    final detectedProject = detect('.mana');
    final detectedMana = detect('scripts');

    return ExplorerConfig(
      projectRoot: value('--project-root', detectedProject),
      manaRoot: value('--mana-root', detectedMana),
      journeyId: args.contains('--journey') ? value('--journey', '') : null,
    );
  }
}

class JourneyStore {
  JourneyStore(this.config);
  final ExplorerConfig config;
  StreamSubscription<FileSystemEvent>? _watch;

  Directory get journeys =>
      Directory('${config.projectRoot}/.mana/learning/journeys');
  Future<List<String>> list() async {
    if (!await journeys.exists()) return [];
    final result =
        (await journeys
                .list()
                .where((item) => item is Directory)
                .map((item) => item.path.split(Platform.pathSeparator).last)
                .toList())
            .cast<String>();
    result.sort();
    return result;
  }

  Future<JourneyGraph> load(String id) async {
    final result = await Process.run(
      '${config.manaRoot}/scripts/mana-journey.sh',
      ['--project-root', config.projectRoot, 'materialize', id],
    );
    if (result.exitCode != 0) throw StateError(result.stderr.toString());
    return JourneyGraph.decode(result.stdout.toString());
  }

  Stream<void> watch(String id) {
    final controller = StreamController<void>();
    final target = Directory('${journeys.path}/$id');
    _watch?.cancel();
    _watch = target
        .watch(recursive: true)
        .listen((_) => controller.add(null), onError: controller.addError);
    controller.onCancel = () => _watch?.cancel();
    return controller.stream;
  }

  Future<List<Map<String, dynamic>>> labels(String id, String node) async {
    final result =
        await Process.run('${config.manaRoot}/scripts/mana-concepts.sh', [
          '--project-root',
          config.projectRoot,
          'labels',
          '--journey',
          id,
          '--node',
          node,
          '--json',
        ]);
    if (result.exitCode != 0) return [];
    return (JourneyGraph.decode('{"labels":${result.stdout}}').raw['labels']
            as List)
        .cast<Map<String, dynamic>>();
  }

  Future<String> requestExpansion(String journey, String node) async {
    final result = await Process.run(
      '${config.manaRoot}/scripts/mana-expand.sh',
      [
        '--project-root',
        config.projectRoot,
        'request',
        '--journey',
        journey,
        '--node',
        node,
      ],
    );
    if (result.exitCode != 0) throw StateError(result.stderr.toString());
    return result.stdout.toString().trim();
  }

  Future<String> loadDiagram(
    String journey,
    Map<String, dynamic> diagram,
  ) async {
    final path = diagram['asset_path'] as String?;
    if (path == null ||
        !RegExp(r'^assets/[A-Za-z0-9._/-]+\.puml$').hasMatch(path)) {
      throw StateError('Invalid diagram asset path.');
    }
    return File('${journeys.path}/$journey/$path').readAsString();
  }
}

class ManaExplorerApp extends StatelessWidget {
  const ManaExplorerApp({super.key, required this.config});
  final ExplorerConfig config;
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Mana Learning Explorer',
    theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
    home: ExplorerPage(
      store: JourneyStore(config),
      initialJourney: config.journeyId,
    ),
  );
}

class ExplorerPage extends StatefulWidget {
  const ExplorerPage({super.key, required this.store, this.initialJourney});
  final JourneyStore store;
  final String? initialJourney;
  @override
  State<ExplorerPage> createState() => _ExplorerPageState();
}

class _ExplorerPageState extends State<ExplorerPage> {
  JourneyGraph? graph;
  String? journeyId, selectedNode, error, source;
  List<String> journeys = [];
  List<Map<String, dynamic>> labels = [];
  StreamSubscription<void>? watcher;

  @override
  void initState() {
    super.initState();
    _open();
  }

  @override
  void dispose() {
    watcher?.cancel();
    super.dispose();
  }

  Future<void> _open([String? requested]) async {
    try {
      journeys = await widget.store.list();
      final id =
          requested ??
          widget.initialJourney ??
          (journeys.isEmpty ? null : journeys.first);
      if (id == null) {
        setState(
          () => error = 'No Journey found under .mana/learning/journeys',
        );
        return;
      }
      final loaded = await widget.store.load(id);
      setState(() {
        journeyId = id;
        graph = loaded;
        selectedNode ??= loaded.nodes.isEmpty
            ? null
            : loaded.nodes.first['id'] as String?;
        error = null;
      });
      watcher?.cancel();
      watcher = widget.store.watch(id).listen((_) => _reload());
      await _select(selectedNode);
    } catch (exception) {
      setState(() => error = exception.toString());
    }
  }

  Future<void> _reload() async {
    if (journeyId != null) await _open(journeyId);
  }

  Future<void> _select(String? id) async {
    if (id == null || graph == null || journeyId == null) return;
    final anchor = graph!.anchorsFor(id).isEmpty
        ? null
        : graph!.anchorsFor(id).first;
    String? loaded;
    if (anchor != null) {
      final file = File('${widget.store.config.projectRoot}/${anchor['path']}');
      if (await file.exists()) {
        loaded = await file.readAsString();
      }
    }
    final conceptLabels = await widget.store.labels(journeyId!, id);
    if (mounted) {
      setState(() {
        selectedNode = id;
        source = loaded;
        labels = conceptLabels;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (error != null) {
      return Scaffold(body: Center(child: Text(error!)));
    }
    if (graph == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final selected = graph!.node(selectedNode!)!;
    return Scaffold(
      appBar: AppBar(
        title: Text(graph!.title),
        actions: [
          DropdownButton<String>(
            value: journeyId,
            items: journeys
                .map((id) => DropdownMenuItem(value: id, child: Text(id)))
                .toList(),
            onChanged: (id) {
              selectedNode = null;
              _open(id);
            },
          ),
          IconButton(
            onPressed: _reload,
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: Row(
        children: [
          SizedBox(width: 320, child: _navigation()),
          const VerticalDivider(width: 1),
          Expanded(child: _detail(selected)),
          const VerticalDivider(width: 1),
          Expanded(child: _source(selected)),
        ],
      ),
    );
  }

  Widget _navigation() => ListView(
    children: graph!.nodes
        .map(
          (node) => ListTile(
            selected: node['id'] == selectedNode,
            title: Text(node['label'] as String? ?? node['id'] as String),
            subtitle: Text(
              '${node['state']} • ${node['disposition'] ?? 'primary'}',
            ),
            leading: Icon(
              node['disposition'] == 'deferred'
                  ? Icons.schedule
                  : Icons.account_tree_outlined,
            ),
            onTap: () => _select(node['id'] as String),
          ),
        )
        .toList(),
  );
  Widget _detail(Map<String, dynamic> node) {
    final explanations = graph!.explanationsFor(node['id'] as String);
    final timeline = graph!.timelineFor(node['id'] as String);
    final diagrams = graph!.diagramsFor(node['id'] as String);
    return Padding(
      padding: const EdgeInsets.all(20),
      child: ListView(
        children: [
          Text(
            node['label'] as String? ?? node['id'] as String,
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          Text('State: ${node['state']} • ${node['disposition'] ?? 'primary'}'),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            children: labels
                .map((item) => Chip(label: Text(item['key'] as String)))
                .toList(),
          ),
          const SizedBox(height: 16),
          Text('Direct paths', style: Theme.of(context).textTheme.titleMedium),
          ...graph!
              .related(node['id'] as String)
              .map(
                (edge) => ListTile(
                  dense: true,
                  title: Text(
                    '${edge['kind']} ${edge['from'] == node['id'] ? '→' : '←'}',
                  ),
                  subtitle: Text(
                    edge['from'] == node['id']
                        ? edge['to'] as String
                        : edge['from'] as String,
                  ),
                ),
              ),
          const SizedBox(height: 12),
          Text('Explanation', style: Theme.of(context).textTheme.titleMedium),
          ...explanations.map(
            (item) => Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Text(
                  item['body'] as String? ??
                      'Explanation available without body.',
                ),
              ),
            ),
          ),
          if (timeline.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(
              'Git timeline',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            ...timeline.map(
              (event) => ListTile(
                dense: true,
                leading: const Icon(Icons.history),
                title: Text(event['summary'] as String),
                subtitle: Text(
                  '${event['revision']} • ${event['occurred_at']}',
                ),
              ),
            ),
          ],
          if (diagrams.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text('Diagrams', style: Theme.of(context).textTheme.titleMedium),
            ...diagrams.map(
              (diagram) => ListTile(
                dense: true,
                leading: const Icon(Icons.account_tree_outlined),
                title: Text(
                  diagram['title'] as String? ?? '${diagram['kind']} diagram',
                ),
                subtitle: Text(
                  '${diagram['kind']} • ${diagram['id']} • selected node ${node['id']}',
                ),
                trailing: const Icon(Icons.open_in_new),
                onTap: () => _openDiagram(diagram),
              ),
            ),
          ],
          FilledButton.icon(
            onPressed: () async {
              try {
                final path = await widget.store.requestExpansion(
                  journeyId!,
                  node['id'] as String,
                );
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('Expansion request created: $path')),
                  );
                }
              } catch (e) {
                if (mounted) {
                  ScaffoldMessenger.of(
                    context,
                  ).showSnackBar(SnackBar(content: Text(e.toString())));
                }
              }
            },
            icon: const Icon(Icons.add_comment_outlined),
            label: const Text('Request explanation'),
          ),
        ],
      ),
    );
  }

  Future<void> _openDiagram(Map<String, dynamic> diagram) async {
    try {
      final contents = await widget.store.loadDiagram(journeyId!, diagram);
      final nodeIds = (diagram['node_ids'] as List? ?? []).cast<String>();
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(diagram['title'] as String? ?? 'Journey diagram'),
          content: SizedBox(
            width: 720,
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Mapped Journey nodes'),
                  Wrap(
                    spacing: 8,
                    children: nodeIds
                        .map(
                          (id) => ActionChip(
                            label: Text(id),
                            onPressed: () {
                              Navigator.pop(context);
                              _select(id);
                            },
                          ),
                        )
                        .toList(),
                  ),
                  const SizedBox(height: 12),
                  SelectableText(
                    contents,
                    style: const TextStyle(fontFamily: 'monospace'),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Close'),
            ),
          ],
        ),
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(error.toString())));
      }
    }
  }

  Widget _source(Map<String, dynamic> node) {
    final anchor = graph!.anchorsFor(node['id'] as String).isEmpty
        ? null
        : graph!.anchorsFor(node['id'] as String).first;
    if (anchor == null) {
      return const Center(child: Text('No source anchor for this node.'));
    }
    final range = anchor['range'] as Map<String, dynamic>;
    final start = range['start_line'] as int, end = range['end_line'] as int;
    final lines = (source ?? '').split('\n');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: Text('${anchor['path']}:$start-$end'),
        ),
        Expanded(
          child: ListView.builder(
            itemCount: lines.length,
            itemBuilder: (context, index) {
              final line = index + 1;
              final selected = line >= start && line <= end;
              return Container(
                color: selected
                    ? Theme.of(context).colorScheme.secondaryContainer
                    : null,
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 1,
                ),
                child: Text(
                  '${line.toString().padLeft(4)}  ${lines[index]}',
                  style: const TextStyle(fontFamily: 'monospace'),
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}
