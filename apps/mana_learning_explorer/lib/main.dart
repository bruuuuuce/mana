import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:re_editor/re_editor.dart';
import 'package:re_highlight/languages/bash.dart';
import 'package:re_highlight/languages/dart.dart';
import 'package:re_highlight/languages/java.dart';
import 'package:re_highlight/languages/javascript.dart';
import 'package:re_highlight/languages/json.dart';
import 'package:re_highlight/languages/kotlin.dart';
import 'package:re_highlight/languages/python.dart';
import 'package:re_highlight/languages/sql.dart';
import 'package:re_highlight/languages/swift.dart';
import 'package:re_highlight/languages/typescript.dart';
import 'package:re_highlight/languages/yaml.dart';
import 'package:re_highlight/styles/atom-one-dark-reasonable.dart';
import 'package:re_highlight/styles/atom-one-light.dart';

import 'journey_graph.dart';
import 'source_workspace.dart';

Future<void> main(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  final config = ExplorerConfig.parse(args);
  final preferences = await ExplorerPreferences.load(config);
  runApp(ManaExplorerApp(config: config, preferences: preferences));
}

class _ReadOnlySourceEditor extends StatefulWidget {
  const _ReadOnlySourceEditor({
    super.key,
    required this.source,
    required this.fontSize,
    required this.tabSize,
    required this.wordWrap,
  });

  final ResolvedSource source;
  final double fontSize;
  final int tabSize;
  final bool wordWrap;

  @override
  State<_ReadOnlySourceEditor> createState() => _ReadOnlySourceEditorState();
}

class _ReadOnlySourceEditorState extends State<_ReadOnlySourceEditor> {
  late final CodeLineEditingController _controller;
  late final CodeScrollController _scrollController;

  @override
  void initState() {
    super.initState();
    _controller = CodeLineEditingController.fromText(
      widget.source.contents,
      CodeLineOptions(indentSize: widget.tabSize),
    );
    _scrollController = CodeScrollController();
    final lines = widget.source.contents!.split('\n');
    final start = (widget.source.location.startLine - 1).clamp(
      0,
      lines.length - 1,
    );
    final end = (widget.source.location.endLine - 1).clamp(
      start,
      lines.length - 1,
    );
    _controller.selection = CodeLineSelection(
      baseIndex: start,
      baseOffset: 0,
      extentIndex: end,
      extentOffset: lines[end].length,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _scrollController.makeCenterIfInvisible(
        CodeLinePosition(index: start, offset: 0),
      );
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final brightness = Theme.of(context).brightness;
    return CodeEditor(
      controller: _controller,
      scrollController: _scrollController,
      readOnly: true,
      showCursorWhenReadOnly: false,
      wordWrap: widget.wordWrap,
      maxLengthSingleLineRendering: 20000,
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
      indicatorBuilder: (context, controller, chunkController, notifier) =>
          DefaultCodeLineNumber(controller: controller, notifier: notifier),
      style: CodeEditorStyle(
        fontFamily: 'monospace',
        fontSize: widget.fontSize,
        backgroundColor: Theme.of(context).colorScheme.surface,
        selectionColor: Theme.of(context).colorScheme.secondaryContainer,
        codeTheme: CodeHighlightTheme(
          languages: _languageModesFor(
            sourceLanguage(widget.source.location.path),
          ),
          theme: brightness == Brightness.dark
              ? atomOneDarkReasonableTheme
              : atomOneLightTheme,
        ),
      ),
    );
  }
}

final Map<String, CodeHighlightThemeMode> _allLanguageModes = {
  'dart': langDart.themeMode,
  'java': langJava.themeMode,
  'kotlin': langKotlin.themeMode,
  'javascript': langJavascript.themeMode,
  'typescript': langTypescript.themeMode,
  'python': langPython.themeMode,
  'bash': langBash.themeMode,
  'json': langJson.themeMode,
  'yaml': langYaml.themeMode,
  'sql': langSql.themeMode,
  'swift': langSwift.themeMode,
};

Map<String, CodeHighlightThemeMode> _languageModesFor(String language) {
  final mode = _allLanguageModes[language];
  return mode == null ? const {} : {language: mode};
}

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

/// Persisted display preferences deliberately live beside the local Journey
/// data.  This keeps the desktop client dependency-free and makes its display
/// choices project-scoped rather than silently global.
class ExplorerPreferences {
  ExplorerPreferences._(
    this._file, {
    required ThemeMode initialMode,
    required this.fontSize,
    required this.tabSize,
    required this.wordWrap,
  }) : themeMode = ValueNotifier(initialMode);

  final File _file;
  final ValueNotifier<ThemeMode> themeMode;
  double fontSize;
  int tabSize;
  bool wordWrap;

  static Future<ExplorerPreferences> load(ExplorerConfig config) async {
    final file = File(
      '${config.projectRoot}/.mana/learning/explorer-preferences.json',
    );
    try {
      final raw = jsonDecode(await file.readAsString()) as Map<String, dynamic>;
      return ExplorerPreferences._(
        file,
        initialMode: _themeMode(raw['themeMode'] as String?),
        fontSize: (raw['editorFontSize'] as num?)?.toDouble() ?? 14,
        tabSize: raw['tabSize'] as int? ?? 2,
        wordWrap: raw['wordWrap'] as bool? ?? false,
      );
    } catch (_) {
      return ExplorerPreferences._(
        file,
        initialMode: ThemeMode.system,
        fontSize: 14,
        tabSize: 2,
        wordWrap: false,
      );
    }
  }

  static ThemeMode _themeMode(String? value) => switch (value) {
    'light' => ThemeMode.light,
    'dark' => ThemeMode.dark,
    _ => ThemeMode.system,
  };

  Future<void> saveThemeMode(ThemeMode value) async {
    themeMode.value = value;
    await _save();
  }

  Future<void> saveDisplay({
    required double fontSize,
    required int tabSize,
    required bool wordWrap,
  }) async {
    this.fontSize = fontSize;
    this.tabSize = tabSize;
    this.wordWrap = wordWrap;
    await _save();
  }

  Future<void> _save() async {
    await _file.parent.create(recursive: true);
    await _file.writeAsString(
      jsonEncode({
        'themeMode': themeMode.value.name,
        'editorFontSize': fontSize,
        'tabSize': tabSize,
        'wordWrap': wordWrap,
      }),
    );
  }
}

class ManaExplorerApp extends StatelessWidget {
  const ManaExplorerApp({
    super.key,
    required this.config,
    required this.preferences,
  });
  final ExplorerConfig config;
  final ExplorerPreferences preferences;
  @override
  Widget build(BuildContext context) => ValueListenableBuilder<ThemeMode>(
    valueListenable: preferences.themeMode,
    builder: (context, mode, _) => MaterialApp(
      title: 'Mana Learning Explorer',
      theme: _theme(Brightness.light),
      darkTheme: _theme(Brightness.dark),
      themeMode: mode,
      home: ExplorerPage(
        store: JourneyStore(config),
        preferences: preferences,
        initialJourney: config.journeyId,
      ),
    ),
  );

  ThemeData _theme(Brightness brightness) => ThemeData(
    colorScheme: ColorScheme.fromSeed(
      seedColor: const Color(0xff4f46e5),
      brightness: brightness,
    ),
    scaffoldBackgroundColor: brightness == Brightness.dark
        ? const Color(0xff101114)
        : const Color(0xfff8f9fc),
    useMaterial3: true,
  );
}

class ExplorerPage extends StatefulWidget {
  const ExplorerPage({
    super.key,
    required this.store,
    required this.preferences,
    this.initialJourney,
  });
  final JourneyStore store;
  final ExplorerPreferences preferences;
  final String? initialJourney;
  @override
  State<ExplorerPage> createState() => _ExplorerPageState();
}

class _ExplorerPageState extends State<ExplorerPage> {
  JourneyGraph? graph;
  String? journeyId, selectedNode, error;
  ResolvedSource? source;
  List<String> journeys = [];
  List<Map<String, dynamic>> labels = [];
  StreamSubscription<void>? watcher;
  bool navigatorVisible = true;
  bool inspectorVisible = true;

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
    final loaded = anchor == null
        ? null
        : await SourceResolver().resolve(
            SourceLocation.fromAnchor(widget.store.config.projectRoot, anchor),
          );
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
        titleSpacing: 20,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(graph!.title, style: Theme.of(context).textTheme.titleMedium),
            Text(
              journeyId ?? '',
              style: Theme.of(context).textTheme.labelSmall,
            ),
          ],
        ),
        actions: [
          const Text('Journey'),
          const SizedBox(width: 8),
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
            onPressed: () => _showDiagramAccess(selected),
            icon: const Icon(Icons.account_tree_outlined),
            tooltip: 'Diagram workspace',
          ),
          IconButton(
            onPressed: _showSettings,
            icon: const Icon(Icons.settings_outlined),
            tooltip: 'Settings',
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
          if (navigatorVisible) ...[
            SizedBox(width: 292, child: _navigatorPanel()),
            const VerticalDivider(width: 1),
          ],
          Expanded(child: _sourceWorkspace(selected)),
          const VerticalDivider(width: 1),
          if (inspectorVisible)
            SizedBox(width: 420, child: _inspectorPanel(selected)),
        ],
      ),
    );
  }

  Widget _panelHeading(String title, VoidCallback onCollapse) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
    child: Row(
      children: [
        Expanded(
          child: Text(title, style: Theme.of(context).textTheme.titleSmall),
        ),
        IconButton(
          visualDensity: VisualDensity.compact,
          onPressed: onCollapse,
          icon: const Icon(Icons.keyboard_double_arrow_left),
          tooltip: 'Collapse panel',
        ),
      ],
    ),
  );

  Widget _navigatorPanel() => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      _panelHeading(
        'JOURNEY NAVIGATOR',
        () => setState(() => navigatorVisible = false),
      ),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Text(
          'All discovered nodes',
          style: Theme.of(context).textTheme.labelMedium,
        ),
      ),
      const SizedBox(height: 6),
      Expanded(
        child: ListView(
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
                        ? Icons.schedule_outlined
                        : Icons.account_tree_outlined,
                  ),
                  onTap: () => _select(node['id'] as String),
                ),
              )
              .toList(),
        ),
      ),
    ],
  );

  Widget _inspectorPanel(Map<String, dynamic> node) {
    final explanations = graph!.explanationsFor(node['id'] as String);
    final timeline = graph!.timelineFor(node['id'] as String);
    final diagrams = graph!.diagramsFor(node['id'] as String);
    return Column(
      children: [
        _panelHeading(
          'INVESTIGATION INSPECTOR',
          () => setState(() => inspectorVisible = false),
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: ListView(
              children: [
                _architectureContext(node, diagrams),
                const SizedBox(height: 18),
                Text(
                  node['label'] as String? ?? node['id'] as String,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                Text(
                  'State: ${node['state']} • ${node['disposition'] ?? 'primary'}',
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  children: labels
                      .map((item) => Chip(label: Text(item['key'] as String)))
                      .toList(),
                ),
                const SizedBox(height: 16),
                Text(
                  'Direct paths',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
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
                Text(
                  'Explanation',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
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
                  Text(
                    'Diagrams',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  ...diagrams.map(
                    (diagram) => ListTile(
                      dense: true,
                      leading: const Icon(Icons.account_tree_outlined),
                      title: Text(
                        diagram['title'] as String? ??
                            '${diagram['kind']} diagram',
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
                          SnackBar(
                            content: Text('Expansion request created: $path'),
                          ),
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
          ),
        ),
      ],
    );
  }

  Widget _architectureContext(
    Map<String, dynamic> node,
    List<Map<String, dynamic>> diagrams,
  ) => Card(
    child: Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.hub_outlined, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Architecture context',
                  style: Theme.of(context).textTheme.titleSmall,
                ),
              ),
              TextButton(
                onPressed: diagrams.isEmpty
                    ? null
                    : () => _openDiagram(diagrams.first),
                child: const Text('Open'),
              ),
            ],
          ),
          Text(
            diagrams.isEmpty
                ? 'No mapped component or execution context is available.'
                : '${diagrams.length} mapped diagram ${diagrams.length == 1 ? 'artifact' : 'artifacts'} available for this node.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    ),
  );

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

  void _showDiagramAccess(Map<String, dynamic> node) {
    final diagrams = graph!.diagramsFor(node['id'] as String);
    if (diagrams.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('No diagram context is mapped to this node.'),
        ),
      );
      return;
    }
    _openDiagram(diagrams.first);
  }

  Future<void> _showSettings() async {
    var mode = widget.preferences.themeMode.value;
    var fontSize = widget.preferences.fontSize;
    var tabSize = widget.preferences.tabSize;
    var wordWrap = widget.preferences.wordWrap;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Display settings'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Theme mode', style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 8),
              SegmentedButton<ThemeMode>(
                segments: const [
                  ButtonSegment(value: ThemeMode.light, label: Text('Light')),
                  ButtonSegment(value: ThemeMode.dark, label: Text('Dark')),
                  ButtonSegment(value: ThemeMode.system, label: Text('System')),
                ],
                selected: {mode},
                onSelectionChanged: (selected) async {
                  final next = selected.single;
                  setDialogState(() => mode = next);
                  await widget.preferences.saveThemeMode(next);
                  if (mounted) setState(() {});
                },
              ),
              const SizedBox(height: 12),
              Text(
                'System follows live operating-system appearance changes.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 20),
              Text(
                'Source display',
                style: Theme.of(context).textTheme.titleSmall,
              ),
              Row(
                children: [
                  const Text('Font size'),
                  Expanded(
                    child: Slider(
                      value: fontSize,
                      min: 11,
                      max: 22,
                      divisions: 11,
                      label: fontSize.round().toString(),
                      onChanged: (value) =>
                          setDialogState(() => fontSize = value),
                      onChangeEnd: (_) async {
                        await widget.preferences.saveDisplay(
                          fontSize: fontSize,
                          tabSize: tabSize,
                          wordWrap: wordWrap,
                        );
                        if (mounted) setState(() {});
                      },
                    ),
                  ),
                  Text(fontSize.round().toString()),
                ],
              ),
              Row(
                children: [
                  const Text('Tab size'),
                  const SizedBox(width: 16),
                  DropdownButton<int>(
                    value: tabSize,
                    items: const [2, 4, 8]
                        .map(
                          (size) => DropdownMenuItem(
                            value: size,
                            child: Text('$size spaces'),
                          ),
                        )
                        .toList(),
                    onChanged: (value) async {
                      setDialogState(() => tabSize = value!);
                      await widget.preferences.saveDisplay(
                        fontSize: fontSize,
                        tabSize: tabSize,
                        wordWrap: wordWrap,
                      );
                      if (mounted) setState(() {});
                    },
                  ),
                ],
              ),
              SwitchListTile.adaptive(
                contentPadding: EdgeInsets.zero,
                title: const Text('Word wrap'),
                value: wordWrap,
                onChanged: (value) async {
                  setDialogState(() => wordWrap = value);
                  await widget.preferences.saveDisplay(
                    fontSize: fontSize,
                    tabSize: tabSize,
                    wordWrap: wordWrap,
                  );
                  if (mounted) setState(() {});
                },
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Done'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _sourceWorkspace(Map<String, dynamic> node) {
    final anchor = graph!.anchorsFor(node['id'] as String).isEmpty
        ? null
        : graph!.anchorsFor(node['id'] as String).first;
    if (anchor == null) {
      return Column(
        children: [
          _sourceHeader(null),
          const Expanded(
            child: Center(child: Text('No source anchor for this node.')),
          ),
        ],
      );
    }
    final resolved = source;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _sourceHeader(anchor),
        Expanded(
          child: resolved == null
              ? const Center(child: CircularProgressIndicator())
              : !resolved.available
              ? Center(child: Text(resolved.status))
              : _ReadOnlySourceEditor(
                  key: ValueKey(
                    '${resolved.location.path}:${resolved.location.revision}:${resolved.contents.hashCode}',
                  ),
                  source: resolved,
                  fontSize: widget.preferences.fontSize,
                  tabSize: widget.preferences.tabSize,
                  wordWrap: widget.preferences.wordWrap,
                ),
        ),
      ],
    );
  }

  Widget _sourceHeader(Map<String, dynamic>? anchor) => Material(
    color: Theme.of(context).colorScheme.surfaceContainerLow,
    child: Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      child: Row(
        children: [
          if (!navigatorVisible)
            IconButton(
              onPressed: () => setState(() => navigatorVisible = true),
              icon: const Icon(Icons.keyboard_double_arrow_right),
              tooltip: 'Show journey navigator',
            ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'SOURCE WORKSPACE',
                  style: Theme.of(context).textTheme.labelLarge,
                ),
                Text(
                  anchor == null
                      ? 'No source selected'
                      : source?.location.reference ??
                            '${anchor['path']}:${(anchor['range'] as Map<String, dynamic>)['start_line']}-${(anchor['range'] as Map<String, dynamic>)['end_line']}',
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                if (source != null)
                  Text(
                    '${source!.status}${source!.location.revision == null ? '' : ' • ${source!.location.revision}'}',
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: source!.drifted
                          ? Theme.of(context).colorScheme.error
                          : null,
                    ),
                  ),
              ],
            ),
          ),
          if (source != null)
            IconButton(
              onPressed: () async {
                await Clipboard.setData(
                  ClipboardData(text: source!.location.reference),
                );
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Source reference copied.')),
                  );
                }
              },
              icon: const Icon(Icons.copy_outlined),
              tooltip: 'Copy reference',
            ),
          if (!inspectorVisible)
            IconButton(
              onPressed: () => setState(() => inspectorVisible = true),
              icon: const Icon(Icons.keyboard_double_arrow_left),
              tooltip: 'Show investigation inspector',
            ),
        ],
      ),
    ),
  );
}
