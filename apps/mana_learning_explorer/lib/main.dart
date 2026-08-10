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
import 'explorer_navigation.dart';
import 'architecture_context.dart';
import 'diagram_detachment.dart';
import 'diagram_workspace.dart';
import 'investigation_inspector.dart';
import 'investigation_prompt.dart';
import 'graph_overview.dart';
import 'journey_navigator.dart';
import 'source_workspace.dart';
import 'external_editor.dart';

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
    required this.externalEditors,
  }) : themeMode = ValueNotifier(initialMode);

  final File _file;
  final ValueNotifier<ThemeMode> themeMode;
  double fontSize;
  int tabSize;
  bool wordWrap;
  ExternalEditorSettings externalEditors;

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
        externalEditors: ExternalEditorSettings.fromJson(
          raw['externalEditors'] as Map<String, dynamic>?,
        ),
      );
    } catch (_) {
      return ExplorerPreferences._(
        file,
        initialMode: ThemeMode.system,
        fontSize: 14,
        tabSize: 2,
        wordWrap: false,
        externalEditors: const ExternalEditorSettings(),
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

  Future<void> saveExternalEditors(ExternalEditorSettings value) async {
    externalEditors = value;
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
        'externalEditors': externalEditors.toJson(),
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

enum ExplorerViewMode { journey, graph }

class _BackIntent extends Intent {
  const _BackIntent();
}

class _ForwardIntent extends Intent {
  const _ForwardIntent();
}

class _ContinueIntent extends Intent {
  const _ContinueIntent();
}

class _ToggleFocusIntent extends Intent {
  const _ToggleFocusIntent();
}

class _OpenDiagramIntent extends Intent {
  const _OpenDiagramIntent();
}

class _CenterOnCurrentIntent extends Intent {
  const _CenterOnCurrentIntent();
}

class _ExplorerPageState extends State<ExplorerPage> {
  JourneyGraph? graph;
  String? journeyId, error;
  ResolvedSource? source;
  List<String> journeys = [];
  List<Map<String, dynamic>> labels = [];
  StreamSubscription<void>? watcher;
  bool navigatorVisible = true;
  bool inspectorVisible = true;
  ExplorerViewMode viewMode = ExplorerViewMode.journey;
  int graphCenterRequest = 0;
  final TraversalState navigation = TraversalState();
  final DiagramViewState diagramViewState = DiagramViewState();
  final ValueNotifier<ExplorerRoute?> currentRoute = ValueNotifier(null);
  final DiagramWindowState diagramWindowState = DiagramWindowState();

  String? get selectedNode => navigation.current?.nodeId;

  @override
  void initState() {
    super.initState();
    _open();
  }

  @override
  void dispose() {
    watcher?.cancel();
    currentRoute.dispose();
    diagramWindowState.dispose();
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
      final current = navigation.current;
      final nextNode =
          current?.journeyId == id && loaded.node(current!.nodeId) != null
          ? current.nodeId
          : loaded.nodes.isEmpty
          ? null
          : loaded.nodes.first['id'] as String?;
      setState(() {
        journeyId = id;
        graph = loaded;
        error = null;
      });
      watcher?.cancel();
      watcher = widget.store.watch(id).listen((_) => _reload());
      if (nextNode != null) {
        if (current?.journeyId != id) {
          navigation.reset(ExplorerRoute(journeyId: id, nodeId: nextNode));
        }
        currentRoute.value = navigation.current;
        await _hydrateRoute(navigation.current!);
      }
    } catch (exception) {
      setState(() => error = exception.toString());
    }
  }

  Future<void> _reload() async {
    if (journeyId != null) await _open(journeyId);
  }

  Future<void> _navigate(ExplorerRoute route) async {
    if (graph == null || route.journeyId != journeyId) return;
    if (graph!.node(route.nodeId) == null) return;
    if (!navigation.navigate(route)) return;
    currentRoute.value = navigation.current;
    setState(() {
      source = null;
      labels = [];
    });
    await _hydrateRoute(route);
  }

  Future<void> _hydrateRoute(ExplorerRoute route) async {
    if (graph == null || route.journeyId != journeyId) return;
    final architecture = ArchitectureContextModel.build(
      graph: graph!,
      nodeId: route.nodeId,
    );
    if (diagramViewState.followCurrent) {
      diagramViewState.focus(architecture.focusedElementId);
    }
    final anchor = graph!.anchorsFor(route.nodeId).isEmpty
        ? null
        : graph!.anchorsFor(route.nodeId).first;
    final location =
        route.sourceLocation ??
        (anchor == null
            ? null
            : SourceLocation.fromAnchor(
                widget.store.config.projectRoot,
                anchor,
              ));
    final loaded = location == null
        ? null
        : await SourceResolver().resolve(location);
    final conceptLabels = await widget.store.labels(
      route.journeyId,
      route.nodeId,
    );
    if (mounted && navigation.current == route) {
      setState(() {
        source = loaded;
        labels = conceptLabels;
      });
    }
  }

  Future<void> _goBack() async {
    final route = navigation.back();
    if (route == null) return;
    currentRoute.value = route;
    setState(() {
      source = null;
      labels = [];
    });
    await _hydrateRoute(route);
  }

  Future<void> _goForward() async {
    final route = navigation.forward();
    if (route == null) return;
    currentRoute.value = route;
    setState(() {
      source = null;
      labels = [];
    });
    await _hydrateRoute(route);
  }

  void _continuePrimary() {
    if (graph == null || selectedNode == null) return;
    final model = JourneyNavigatorModel.build(
      graph: graph!,
      currentNodeId: selectedNode!,
      visitedNodeIds: navigation.visitedNodeIds,
    );
    if (model.primary.length == 1) {
      _navigate(
        ExplorerRoute(journeyId: journeyId!, nodeId: model.primary.single.id),
      );
    }
  }

  void _toggleFocusMode() => setState(() {
    final enteringFocus = navigatorVisible || inspectorVisible;
    navigatorVisible = !enteringFocus;
    inspectorVisible = !enteringFocus;
  });

  void _centerOnCurrent() {
    if (viewMode == ExplorerViewMode.graph) {
      setState(() => graphCenterRequest++);
    }
  }

  Future<void> _copyToClipboard(String text, String label) async {
    await Clipboard.setData(ClipboardData(text: text));
    if (mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('$label copied.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Mana Learning Explorer')),
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, size: 42),
                  const SizedBox(height: 12),
                  const Text('Could not open this Journey'),
                  const SizedBox(height: 8),
                  SelectableText(error!, textAlign: TextAlign.center),
                  const SizedBox(height: 16),
                  FilledButton.icon(
                    onPressed: _reload,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Try again'),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    }
    if (graph == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final selected = graph!.node(selectedNode!)!;
    return Shortcuts(
      shortcuts: const {
        SingleActivator(LogicalKeyboardKey.arrowLeft, alt: true): _BackIntent(),
        SingleActivator(LogicalKeyboardKey.arrowRight, alt: true):
            _ForwardIntent(),
        SingleActivator(LogicalKeyboardKey.arrowDown, alt: true):
            _ContinueIntent(),
        SingleActivator(LogicalKeyboardKey.keyF, control: true, shift: true):
            _ToggleFocusIntent(),
        SingleActivator(LogicalKeyboardKey.keyD, control: true):
            _OpenDiagramIntent(),
        SingleActivator(LogicalKeyboardKey.keyL, control: true):
            _CenterOnCurrentIntent(),
      },
      child: Actions(
        actions: {
          _BackIntent: CallbackAction<_BackIntent>(onInvoke: (_) => _goBack()),
          _ForwardIntent: CallbackAction<_ForwardIntent>(
            onInvoke: (_) => _goForward(),
          ),
          _ContinueIntent: CallbackAction<_ContinueIntent>(
            onInvoke: (_) => _continuePrimary(),
          ),
          _ToggleFocusIntent: CallbackAction<_ToggleFocusIntent>(
            onInvoke: (_) => _toggleFocusMode(),
          ),
          _OpenDiagramIntent: CallbackAction<_OpenDiagramIntent>(
            onInvoke: (_) => _showDiagramAccess(selected),
          ),
          _CenterOnCurrentIntent: CallbackAction<_CenterOnCurrentIntent>(
            onInvoke: (_) => _centerOnCurrent(),
          ),
        },
        child: Focus(
          autofocus: true,
          child: Scaffold(
            appBar: AppBar(
              titleSpacing: 20,
              title: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    graph!.title,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  Text(
                    journeyId ?? '',
                    style: Theme.of(context).textTheme.labelSmall,
                  ),
                ],
              ),
              actions: [
                SegmentedButton<ExplorerViewMode>(
                  segments: const [
                    ButtonSegment(
                      value: ExplorerViewMode.journey,
                      label: Text('Journey'),
                    ),
                    ButtonSegment(
                      value: ExplorerViewMode.graph,
                      label: Text('Graph'),
                    ),
                  ],
                  selected: {viewMode},
                  onSelectionChanged: (value) =>
                      setState(() => viewMode = value.single),
                ),
                const SizedBox(width: 12),
                DropdownButton<String>(
                  value: journeyId,
                  items: journeys
                      .map((id) => DropdownMenuItem(value: id, child: Text(id)))
                      .toList(),
                  onChanged: (id) {
                    if (id != null) _open(id);
                  },
                ),
                IconButton(
                  onPressed: () => _showDiagramAccess(selected),
                  icon: const Icon(Icons.account_tree_outlined),
                  tooltip: 'Diagram workspace (Ctrl+D)',
                ),
                IconButton(
                  onPressed: _toggleFocusMode,
                  icon: Icon(
                    navigatorVisible || inspectorVisible
                        ? Icons.center_focus_strong_outlined
                        : Icons.center_focus_weak_outlined,
                  ),
                  tooltip: navigatorVisible || inspectorVisible
                      ? 'Focus mode: hide side panels (Ctrl+Shift+F)'
                      : 'Exit focus mode (Ctrl+Shift+F)',
                ),
                IconButton(
                  onPressed: () => _copyToClipboard(selectedNode!, 'Node ID'),
                  icon: const Icon(Icons.tag),
                  tooltip: 'Copy node ID',
                ),
                IconButton(
                  onPressed: () => _copyToClipboard(journeyId!, 'Journey ID'),
                  icon: const Icon(Icons.copy_all_outlined),
                  tooltip: 'Copy journey ID',
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
                Expanded(
                  child: viewMode == ExplorerViewMode.journey
                      ? _sourceWorkspace(selected)
                      : JourneyGraphOverview(
                          graph: graph!,
                          currentNodeId: selectedNode!,
                          visitedNodeIds: navigation.visitedNodeIds,
                          onNodeSelected: (nodeId) => _navigate(
                            ExplorerRoute(
                              journeyId: journeyId!,
                              nodeId: nodeId,
                            ),
                          ),
                          onRelationSelected: _showGraphRelation,
                          centerRequest: graphCenterRequest,
                        ),
                ),
                const VerticalDivider(width: 1),
                if (inspectorVisible)
                  SizedBox(width: 420, child: _inspectorPanel(selected)),
              ],
            ),
            bottomNavigationBar: _traversalBar(),
          ),
        ),
      ),
    );
  }

  Widget _traversalBar() => Material(
    color: Theme.of(context).colorScheme.surfaceContainerLow,
    child: SafeArea(
      top: false,
      child: SizedBox(
        height: 48,
        child: Row(
          children: [
            TextButton.icon(
              onPressed: navigation.canGoBack ? _goBack : null,
              icon: const Icon(Icons.arrow_back),
              label: const Text('Back'),
            ),
            Expanded(
              child: Center(
                child: Text(
                  _breadcrumb(),
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            ),
            TextButton.icon(
              onPressed: navigation.canGoForward ? _goForward : null,
              icon: const Icon(Icons.arrow_forward),
              label: const Text('Forward'),
            ),
          ],
        ),
      ),
    ),
  );

  Future<void> _showGraphRelation(GraphRelation relation) => showDialog<void>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: const Text('Graph relation'),
      content: Text(
        '${relation.kind} · ${relation.style.name}\n${relation.from} → ${relation.to}',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(dialogContext),
          child: const Text('Close'),
        ),
        FilledButton(
          onPressed: () {
            Navigator.pop(dialogContext);
            _navigate(
              ExplorerRoute(journeyId: journeyId!, nodeId: relation.to),
            );
          },
          child: const Text('Open target'),
        ),
      ],
    ),
  );

  String _breadcrumb() {
    final route = navigation.current;
    if (route == null || graph == null) return 'No selected node';
    final path = graph!.logicalPathFor(route.nodeId);
    final labels = path
        .map((id) => graph!.node(id)?['label'] as String? ?? id)
        .toList();
    return labels.isEmpty ? route.nodeId : labels.join('  ›  ');
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

  Widget _navigatorPanel() {
    final model = JourneyNavigatorModel.build(
      graph: graph!,
      currentNodeId: selectedNode!,
      visitedNodeIds: navigation.visitedNodeIds,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _panelHeading(
          'JOURNEY NAVIGATOR',
          () => setState(() => navigatorVisible = false),
        ),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.only(bottom: 12),
            children: [
              _navigatorSection('CURRENT PATH'),
              ...model.currentPath.map(_navigatorItem),
              if (model.isTerminal)
                _navigatorMessage(
                  Icons.flag_outlined,
                  'Terminal point for this branch',
                ),
              if (model.primary.isNotEmpty) ...[
                _navigatorSection(
                  model.primary.length == 1 ? 'CONTINUE' : 'CHOOSE NEXT',
                ),
                ...model.primary.map(_navigatorItem),
              ],
              if (model.alternatives.isNotEmpty) ...[
                _navigatorSection('ALTERNATIVES'),
                ...model.alternatives.map(_navigatorItem),
              ],
              if (model.deferred.isNotEmpty)
                ExpansionTile(
                  initiallyExpanded: false,
                  leading: const Icon(Icons.schedule_outlined),
                  title: Text('Deferred (${model.deferred.length})'),
                  children: model.deferred.map(_navigatorItem).toList(),
                ),
              if (model.related.isNotEmpty) ...[
                _navigatorSection('RELATED'),
                ...model.related.map(_navigatorItem),
              ],
              if (model.visitedOutsidePath.isNotEmpty)
                ExpansionTile(
                  initiallyExpanded: false,
                  leading: const Icon(Icons.history),
                  title: Text('Visited (${model.visitedOutsidePath.length})'),
                  children: model.visitedOutsidePath
                      .map(_navigatorItem)
                      .toList(),
                ),
              if (model.explorable.isNotEmpty)
                ExpansionTile(
                  initiallyExpanded: false,
                  leading: const Icon(Icons.explore_outlined),
                  title: Text(
                    'Explore known nodes (${model.explorable.length})',
                  ),
                  children: model.explorable.map(_navigatorItem).toList(),
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _navigatorSection(String title) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
    child: Text(title, style: Theme.of(context).textTheme.labelMedium),
  );

  Widget _navigatorMessage(IconData icon, String message) =>
      ListTile(dense: true, leading: Icon(icon), title: Text(message));

  Widget _navigatorItem(JourneyNavigatorItem item) {
    final colors = Theme.of(context).colorScheme;
    final role = switch (item.role) {
      JourneyPathRole.primary => 'Primary',
      JourneyPathRole.alternative => 'Alternative',
      JourneyPathRole.deferred => 'Deferred',
      JourneyPathRole.related => 'Related',
    };
    final icon = switch (item.role) {
      JourneyPathRole.primary => Icons.arrow_forward_outlined,
      JourneyPathRole.alternative => Icons.alt_route_outlined,
      JourneyPathRole.deferred => Icons.schedule_outlined,
      JourneyPathRole.related => Icons.account_tree_outlined,
    };
    return ListTile(
      dense: true,
      selected: item.isCurrent,
      leading: Icon(icon),
      title: Text(item.label, maxLines: 2, overflow: TextOverflow.ellipsis),
      subtitle: Text(
        [
          if (item.isCurrent) 'Current',
          if (item.isVisited && !item.isCurrent) 'Visited',
          item.state,
          role,
          if (item.relationHint != null) item.relationHint!,
        ].join(' • '),
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: item.isCurrent
          ? Icon(Icons.my_location, color: colors.primary, size: 18)
          : null,
      onTap: () =>
          _navigate(ExplorerRoute(journeyId: journeyId!, nodeId: item.id)),
    );
  }

  Widget _inspectorPanel(Map<String, dynamic> node) {
    final diagrams = graph!.diagramsFor(node['id'] as String);
    final model = InvestigationInspectorModel.build(
      graph: graph!,
      nodeId: node['id'] as String,
      projectRoot: widget.store.config.projectRoot,
    );
    final architecture = ArchitectureContextModel.build(
      graph: graph!,
      nodeId: node['id'] as String,
    );
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
                _architectureContext(architecture),
                const SizedBox(height: 18),
                _whyThisNode(node, model),
                const SizedBox(height: 16),
                _evidenceSection(model),
                const SizedBox(height: 16),
                _relationsSection(model),
                const SizedBox(height: 16),
                _promptHandoffSection(),
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
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _whyThisNode(
    Map<String, dynamic> node,
    InvestigationInspectorModel model,
  ) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text('WHY THIS NODE', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 6),
      Text(
        node['label'] as String? ?? node['id'] as String,
        style: Theme.of(context).textTheme.headlineSmall,
      ),
      Text(
        'State: ${node['state'] ?? 'discovered'} • ${node['disposition'] ?? 'primary'}',
      ),
      if (labels.isNotEmpty) ...[
        const SizedBox(height: 8),
        Wrap(
          spacing: 6,
          runSpacing: 4,
          children: labels
              .map((item) => Chip(label: Text(item['key'] as String)))
              .toList(),
        ),
      ],
      ...model.hypotheses.map(
        (hypothesis) => Card(
          child: Padding(
            padding: const EdgeInsets.all(10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(hypothesis['claim'] as String? ?? 'Hypothesis'),
                const SizedBox(height: 4),
                Text(
                  '${hypothesis['confidence'] ?? 'unknown'} • ${hypothesis['category'] ?? 'unknown'}',
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ],
            ),
          ),
        ),
      ),
      ...model.explanations.map(
        (explanation) => Card(
          child: Padding(
            padding: const EdgeInsets.all(10),
            child: Text(
              explanation['body'] as String? ??
                  'Explanation available without body.',
            ),
          ),
        ),
      ),
      if (model.explanations.isEmpty && model.hypotheses.isEmpty)
        Text(
          'No rationale was recorded for this node.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
    ],
  );

  Widget _evidenceSection(InvestigationInspectorModel model) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text('EVIDENCE', style: Theme.of(context).textTheme.titleMedium),
      if (model.evidence.isEmpty)
        Padding(
          padding: const EdgeInsets.only(top: 6),
          child: Text(
            'No evidence is linked to this node.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
      ...model.evidence.map(
        (evidence) => Card(
          child: ListTile(
            enabled: evidence.location != null,
            leading: const Icon(Icons.fact_check_outlined),
            title: Text(evidence.summary),
            subtitle: Text(
              [
                evidence.kind,
                if (evidence.relationship != null) evidence.relationship!,
                if (evidence.location != null) evidence.location!.reference,
                evidence.id,
              ].join(' • '),
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
            ),
            trailing: evidence.location == null
                ? const Icon(Icons.link_off_outlined)
                : const Icon(Icons.open_in_new),
            onTap: evidence.location == null
                ? null
                : () => _navigate(
                    ExplorerRoute(
                      journeyId: journeyId!,
                      nodeId: selectedNode!,
                      evidenceId: evidence.id,
                      sourceLocation: evidence.location,
                    ),
                  ),
          ),
        ),
      ),
    ],
  );

  Widget _relationsSection(InvestigationInspectorModel model) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        'RELATIONS / NEXT HOPS',
        style: Theme.of(context).textTheme.titleMedium,
      ),
      if (model.isTerminal)
        _navigatorMessage(
          Icons.flag_outlined,
          'Terminal point for this branch',
        ),
      _relationGroup(
        model.primary.length == 1 ? 'CONTINUE' : 'CHOOSE NEXT',
        model.primary,
      ),
      _relationGroup('ALTERNATIVES', model.alternatives),
      _relationGroup('DEFERRED', model.deferred, subdued: true),
      _relationGroup('RELATED', model.related),
      _relationGroup('CAME FROM', model.cameFrom),
    ],
  );

  Widget _promptHandoffSection() => Card(
    child: Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          const Icon(Icons.content_paste_search_outlined),
          const SizedBox(width: 10),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('INVESTIGATION HANDOFF'),
                Text(
                  'Preview and copy a local context prompt for an external agent.',
                ),
              ],
            ),
          ),
          TextButton(
            onPressed: _showPromptHandoff,
            child: const Text('Preview'),
          ),
        ],
      ),
    ),
  );

  String _investigationPrompt(String requestedGoal) {
    final route = navigation.current!;
    return const InvestigationPromptBuilder().build(
      graph: graph!,
      route: route,
      projectRoot: widget.store.config.projectRoot,
      requestedGoal: requestedGoal,
      displayedSource: source,
      selectedDiagramElementId: diagramViewState.focusedElementId,
    );
  }

  Future<void> _showPromptHandoff() async {
    final goal = TextEditingController();
    try {
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => StatefulBuilder(
          builder: (context, setDialogState) {
            final prompt = _investigationPrompt(goal.text);
            return AlertDialog(
              title: const Text('Investigation prompt handoff'),
              content: SizedBox(
                width: 760,
                height: 600,
                child: Column(
                  children: [
                    TextField(
                      controller: goal,
                      decoration: const InputDecoration(
                        labelText: 'Requested investigation goal',
                        hintText:
                            'For example: identify the next source-backed step.',
                      ),
                      onChanged: (_) => setDialogState(() {}),
                    ),
                    const SizedBox(height: 12),
                    Expanded(
                      child: Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          border: Border.all(
                            color: Theme.of(context).colorScheme.outlineVariant,
                          ),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: SingleChildScrollView(
                          child: SelectableText(
                            prompt,
                            style: const TextStyle(fontFamily: 'monospace'),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(dialogContext),
                  child: const Text('Close'),
                ),
                FilledButton.icon(
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: prompt));
                    if (dialogContext.mounted) Navigator.pop(dialogContext);
                    if (mounted) {
                      ScaffoldMessenger.of(this.context).showSnackBar(
                        const SnackBar(
                          content: Text('Investigation prompt copied.'),
                        ),
                      );
                    }
                  },
                  icon: const Icon(Icons.copy_outlined),
                  label: const Text('Copy prompt'),
                ),
              ],
            );
          },
        ),
      );
    } finally {
      goal.dispose();
    }
  }

  Widget _relationGroup(
    String title,
    List<InspectorRelation> relations, {
    bool subdued = false,
  }) {
    if (relations.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 10),
          child: Text(title, style: Theme.of(context).textTheme.labelMedium),
        ),
        ...relations.map(
          (relation) => Opacity(
            opacity: subdued ? .68 : 1,
            child: title == 'CONTINUE'
                ? Card(
                    color: Theme.of(context).colorScheme.primaryContainer,
                    child: ListTile(
                      leading: const Icon(Icons.arrow_forward),
                      title: Text('Continue to ${relation.label}'),
                      subtitle: Text('${relation.kind} • ${relation.targetId}'),
                      onTap: () => _navigate(
                        ExplorerRoute(
                          journeyId: journeyId!,
                          nodeId: relation.targetId,
                        ),
                      ),
                    ),
                  )
                : ListTile(
                    dense: true,
                    leading: Icon(
                      relation.incoming
                          ? Icons.arrow_back
                          : Icons.arrow_forward,
                    ),
                    title: Text(relation.label),
                    subtitle: Text('${relation.kind} • ${relation.targetId}'),
                    onTap: () => _navigate(
                      ExplorerRoute(
                        journeyId: journeyId!,
                        nodeId: relation.targetId,
                      ),
                    ),
                  ),
          ),
        ),
      ],
    );
  }

  Widget _architectureContext(ArchitectureContextModel model) => Card(
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
                onPressed: model.diagrams.isEmpty
                    ? null
                    : () => _openDiagram(_diagramFor(model)),
                child: const Text('Open'),
              ),
            ],
          ),
          if (model.hasComponents || model.hasSequence) ...[
            const SizedBox(height: 8),
            SegmentedButton<ArchitectureViewKind>(
              segments: [
                ButtonSegment(
                  value: ArchitectureViewKind.components,
                  label: const Text('Components'),
                  enabled: model.hasComponents,
                ),
                ButtonSegment(
                  value: ArchitectureViewKind.sequence,
                  label: const Text('Sequence'),
                  enabled: model.hasSequence,
                ),
              ],
              selected: {
                diagramViewState.kind == ArchitectureViewKind.components &&
                        !model.hasComponents
                    ? ArchitectureViewKind.sequence
                    : diagramViewState.kind,
              },
              onSelectionChanged: (value) =>
                  setState(() => diagramViewState.kind = value.single),
            ),
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                _activeArchitectureSummary(model),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
          ],
          const SizedBox(height: 8),
          Text(
            model.statusMessage,
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (model.component != null)
            _contextLine('Component', model.component!),
          if (model.participant != null)
            _contextLine('Participant', model.participant!),
          if (model.executionPath.isNotEmpty)
            _contextLine('Execution', model.executionPath.join('  ›  ')),
          if (model.step != null || model.depth != null)
            _contextLine(
              'Step',
              '${model.step ?? 'current'}${model.depth == null ? '' : ' • depth ${model.depth}'}',
            ),
          if (model.transitionKind != null)
            _contextLine(
              'Boundary',
              model.isAsync
                  ? '${model.transitionKind} boundary (not a synchronous stack)'
                  : model.transitionKind!,
            ),
          if (model.provenance != null)
            _contextLine('Snapshot', model.provenance!),
          if (model.status == ArchitectureContextStatus.mapped ||
              model.status == ArchitectureContextStatus.inferred)
            SwitchListTile.adaptive(
              contentPadding: EdgeInsets.zero,
              dense: true,
              title: const Text('Follow current'),
              value: diagramViewState.followCurrent,
              onChanged: (value) =>
                  setState(() => diagramViewState.followCurrent = value),
            ),
        ],
      ),
    ),
  );

  Widget _contextLine(String label, String value) => Padding(
    padding: const EdgeInsets.only(top: 4),
    child: Text('$label: $value', style: Theme.of(context).textTheme.bodySmall),
  );

  Map<String, dynamic> _diagramFor(ArchitectureContextModel model) =>
      model.diagrams.firstWhere(
        (diagram) => diagram['kind'] == diagramViewState.kind.name,
        orElse: () => model.diagrams.first,
      );

  String _activeArchitectureSummary(ArchitectureContextModel model) {
    final diagram = _diagramFor(model);
    final kind = diagram['kind'] as String? ?? 'diagram';
    final title = diagram['title'] as String? ?? '$kind context';
    return '${kind == 'component' ? 'Components' : 'Sequence'}: $title';
  }

  Future<void> _openDiagram(Map<String, dynamic> diagram) async {
    if (graph == null || currentRoute.value == null) return;
    final related = graph!.diagramsFor(currentRoute.value!.nodeId);
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(diagram['title'] as String? ?? 'Diagram Workspace'),
        content: SizedBox(
          width: 1100,
          height: 760,
          child: DiagramWorkspace(
            graph: graph!,
            diagrams: related.isEmpty ? [diagram] : related,
            currentRoute: currentRoute,
            onNavigate: _navigate,
            windowState: diagramWindowState,
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
            TextButton.icon(
              onPressed: () => _showExternalEditorSettings(dialogContext),
              icon: const Icon(Icons.open_in_new),
              label: const Text('External editors'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Done'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _showExternalEditorSettings(BuildContext parentContext) async {
    var settings = widget.preferences.externalEditors;
    await showDialog<void>(
      context: parentContext,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('External editor profiles'),
          content: SizedBox(
            width: 680,
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'The most specific match wins: path override, extension, language, then default.',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  const SizedBox(height: 12),
                  _editorProfileList(
                    settings,
                    setDialogState,
                    (next) => settings = next,
                  ),
                  const Divider(height: 28),
                  _editorMappings(
                    settings,
                    setDialogState,
                    (next) => settings = next,
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () async {
                await widget.preferences.saveExternalEditors(settings);
                if (mounted) setState(() {});
                if (dialogContext.mounted) Navigator.pop(dialogContext);
              },
              child: const Text('Save'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _editorProfileList(
    ExternalEditorSettings settings,
    StateSetter refresh,
    ValueChanged<ExternalEditorSettings> replace,
  ) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text('Profiles', style: Theme.of(context).textTheme.titleSmall),
      ...settings.profiles.map(
        (profile) => ListTile(
          dense: true,
          title: Text(profile.name),
          subtitle: Text(
            profile.isUriProfile
                ? profile.uriTemplate!
                : '${profile.executable} ${profile.arguments.join(' ')}',
          ),
          trailing: Wrap(
            spacing: 2,
            children: [
              IconButton(
                tooltip: 'Test profile',
                icon: const Icon(Icons.play_circle_outline),
                onPressed: () => _testEditorProfile(profile),
              ),
              IconButton(
                tooltip: 'Remove profile',
                icon: const Icon(Icons.delete_outline),
                onPressed: () {
                  final profiles = [...settings.profiles]
                    ..removeWhere((p) => p.id == profile.id);
                  final next = ExternalEditorSettings(
                    profiles: profiles,
                    defaultProfileId: settings.defaultProfileId == profile.id
                        ? null
                        : settings.defaultProfileId,
                    extensionProfiles: Map.of(settings.extensionProfiles)
                      ..removeWhere((_, id) => id == profile.id),
                    languageProfiles: Map.of(settings.languageProfiles)
                      ..removeWhere((_, id) => id == profile.id),
                    pathOverrides: settings.pathOverrides
                        .where((item) => item.profileId != profile.id)
                        .toList(),
                  );
                  replace(next);
                  refresh(() {});
                },
              ),
            ],
          ),
        ),
      ),
      TextButton.icon(
        onPressed: () => _addEditorProfile(settings, refresh, replace),
        icon: const Icon(Icons.add),
        label: const Text('Add profile'),
      ),
    ],
  );

  Widget _editorMappings(
    ExternalEditorSettings settings,
    StateSetter refresh,
    ValueChanged<ExternalEditorSettings> replace,
  ) {
    final ids = settings.profiles.map((profile) => profile.id).toList();
    Widget selector(
      String label,
      String? value,
      ValueChanged<String?> changed,
    ) => Row(
      children: [
        SizedBox(width: 150, child: Text(label)),
        Expanded(
          child: DropdownButton<String?>(
            isExpanded: true,
            value: value,
            items: [
              const DropdownMenuItem<String?>(value: null, child: Text('None')),
              ...settings.profiles.map(
                (p) =>
                    DropdownMenuItem<String?>(value: p.id, child: Text(p.name)),
              ),
            ],
            onChanged: ids.isEmpty ? null : changed,
          ),
        ),
      ],
    );
    ExternalEditorSettings next({
      String? defaultId,
      Map<String, String>? extensions,
      Map<String, String>? languages,
      List<EditorPathOverride>? paths,
    }) => ExternalEditorSettings(
      profiles: settings.profiles,
      defaultProfileId: defaultId ?? settings.defaultProfileId,
      extensionProfiles: extensions ?? settings.extensionProfiles,
      languageProfiles: languages ?? settings.languageProfiles,
      pathOverrides: paths ?? settings.pathOverrides,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Mappings', style: Theme.of(context).textTheme.titleSmall),
        selector('Default fallback', settings.defaultProfileId, (id) {
          replace(
            ExternalEditorSettings(
              profiles: settings.profiles,
              defaultProfileId: id,
              extensionProfiles: settings.extensionProfiles,
              languageProfiles: settings.languageProfiles,
              pathOverrides: settings.pathOverrides,
            ),
          );
          refresh(() {});
        }),
        _mappingRows(
          'Extension',
          settings.extensionProfiles,
          settings,
          refresh,
          replace,
          (map) => next(extensions: map),
        ),
        _mappingRows(
          'Language',
          settings.languageProfiles,
          settings,
          refresh,
          replace,
          (map) => next(languages: map),
        ),
        Text('Path overrides', style: Theme.of(context).textTheme.labelLarge),
        ...settings.pathOverrides.map(
          (override) => Row(
            children: [
              Expanded(child: Text(override.pathPrefix)),
              SizedBox(
                width: 180,
                child: Text(_profileName(settings, override.profileId)),
              ),
              IconButton(
                icon: const Icon(Icons.close),
                tooltip: 'Remove override',
                onPressed: () {
                  replace(
                    next(
                      paths: settings.pathOverrides
                          .where((item) => item != override)
                          .toList(),
                    ),
                  );
                  refresh(() {});
                },
              ),
            ],
          ),
        ),
        TextButton.icon(
          onPressed: ids.isEmpty
              ? null
              : () => _addPathOverride(settings, refresh, replace),
          icon: const Icon(Icons.add),
          label: const Text('Add path override'),
        ),
      ],
    );
  }

  Widget _mappingRows(
    String type,
    Map<String, String> mappings,
    ExternalEditorSettings settings,
    StateSetter refresh,
    ValueChanged<ExternalEditorSettings> replace,
    ExternalEditorSettings Function(Map<String, String>) build,
  ) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text('$type mappings', style: Theme.of(context).textTheme.labelLarge),
      ...mappings.entries.map(
        (entry) => Row(
          children: [
            SizedBox(width: 150, child: Text(entry.key)),
            Expanded(child: Text(_profileName(settings, entry.value))),
            IconButton(
              icon: const Icon(Icons.close),
              tooltip: 'Remove mapping',
              onPressed: () {
                final map = Map.of(mappings)..remove(entry.key);
                replace(build(map));
                refresh(() {});
              },
            ),
          ],
        ),
      ),
      TextButton.icon(
        onPressed: settings.profiles.isEmpty
            ? null
            : () => _addMapping(type, settings, refresh, replace, build),
        icon: const Icon(Icons.add),
        label: Text('Add $type mapping'),
      ),
    ],
  );

  String _profileName(ExternalEditorSettings settings, String id) {
    for (final profile in settings.profiles) {
      if (profile.id == id) return profile.name;
    }
    return id;
  }

  Future<void> _addEditorProfile(
    ExternalEditorSettings settings,
    StateSetter refresh,
    ValueChanged<ExternalEditorSettings> replace,
  ) async {
    final name = TextEditingController();
    final executable = TextEditingController();
    final arguments = TextEditingController(
      text: '--goto {file}:{line}:{column}',
    );
    final uri = TextEditingController();
    final profile = await showDialog<ExternalEditorProfile>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Add editor profile'),
        content: SizedBox(
          width: 460,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: name,
                decoration: const InputDecoration(labelText: 'Name'),
              ),
              TextField(
                controller: executable,
                decoration: const InputDecoration(labelText: 'Executable'),
              ),
              TextField(
                controller: arguments,
                maxLines: 3,
                decoration: const InputDecoration(
                  labelText: 'Arguments, one per line',
                ),
              ),
              TextField(
                controller: uri,
                decoration: const InputDecoration(
                  labelText: 'URI template (optional alternative)',
                ),
              ),
              const Text(
                'Placeholders: {file}, {path}, {line}, {column}, {projectRoot}.',
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              final id = name.text.trim().toLowerCase().replaceAll(
                RegExp(r'[^a-z0-9]+'),
                '-',
              );
              final value = ExternalEditorProfile(
                id: id,
                name: name.text.trim(),
                executable: executable.text.trim().isEmpty
                    ? null
                    : executable.text.trim(),
                arguments: arguments.text
                    .split('\n')
                    .where((item) => item.isNotEmpty)
                    .toList(),
                uriTemplate: uri.text.trim().isEmpty ? null : uri.text.trim(),
              );
              if (value.isValid &&
                  !settings.profiles.any((item) => item.id == id)) {
                Navigator.pop(context, value);
              }
            },
            child: const Text('Add'),
          ),
        ],
      ),
    );
    if (profile == null) return;
    replace(
      ExternalEditorSettings(
        profiles: [...settings.profiles, profile],
        defaultProfileId: settings.defaultProfileId,
        extensionProfiles: settings.extensionProfiles,
        languageProfiles: settings.languageProfiles,
        pathOverrides: settings.pathOverrides,
      ),
    );
    refresh(() {});
  }

  Future<void> _addMapping(
    String type,
    ExternalEditorSettings settings,
    StateSetter refresh,
    ValueChanged<ExternalEditorSettings> replace,
    ExternalEditorSettings Function(Map<String, String>) build,
  ) async {
    final key = TextEditingController();
    String id = settings.profiles.first.id;
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: Text('Add $type mapping'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: key,
                decoration: InputDecoration(
                  labelText: type == 'Extension'
                      ? 'Extension (without dot)'
                      : 'Detected language',
                ),
              ),
              DropdownButton<String>(
                isExpanded: true,
                value: id,
                items: settings.profiles
                    .map(
                      (p) => DropdownMenuItem(value: p.id, child: Text(p.name)),
                    )
                    .toList(),
                onChanged: (value) => setState(() => id = value!),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () =>
                  Navigator.pop(context, key.text.trim().isNotEmpty),
              child: const Text('Add'),
            ),
          ],
        ),
      ),
    );
    if (accepted != true) return;
    final map = type == 'Extension'
        ? Map.of(settings.extensionProfiles)
        : Map.of(settings.languageProfiles);
    map[key.text.trim().toLowerCase()] = id;
    replace(build(map));
    refresh(() {});
  }

  Future<void> _addPathOverride(
    ExternalEditorSettings settings,
    StateSetter refresh,
    ValueChanged<ExternalEditorSettings> replace,
  ) async {
    final path = TextEditingController();
    String id = settings.profiles.first.id;
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: const Text('Add path override'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: path,
                decoration: const InputDecoration(
                  labelText: 'Project-relative path prefix',
                ),
              ),
              DropdownButton<String>(
                isExpanded: true,
                value: id,
                items: settings.profiles
                    .map(
                      (p) => DropdownMenuItem(value: p.id, child: Text(p.name)),
                    )
                    .toList(),
                onChanged: (value) => setState(() => id = value!),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () =>
                  Navigator.pop(context, path.text.trim().isNotEmpty),
              child: const Text('Add'),
            ),
          ],
        ),
      ),
    );
    if (accepted != true) return;
    replace(
      ExternalEditorSettings(
        profiles: settings.profiles,
        defaultProfileId: settings.defaultProfileId,
        extensionProfiles: settings.extensionProfiles,
        languageProfiles: settings.languageProfiles,
        pathOverrides: [
          ...settings.pathOverrides,
          EditorPathOverride(pathPrefix: path.text.trim(), profileId: id),
        ],
      ),
    );
    refresh(() {});
  }

  Future<void> _testEditorProfile(ExternalEditorProfile profile) async {
    try {
      await const ExternalEditorLauncher().test(
        profile,
        widget.store.config.projectRoot,
      );
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('${profile.name} launched.')));
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not launch ${profile.name}: $error')),
        );
      }
    }
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
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.source_outlined, size: 36),
                      const SizedBox(height: 8),
                      Text(resolved.status, textAlign: TextAlign.center),
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        onPressed: navigation.canGoBack ? _goBack : _reload,
                        icon: Icon(
                          navigation.canGoBack
                              ? Icons.arrow_back
                              : Icons.refresh,
                        ),
                        label: Text(
                          navigation.canGoBack
                              ? 'Back to previous node'
                              : 'Reload Journey',
                        ),
                      ),
                    ],
                  ),
                )
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
          if (source != null)
            IconButton(
              onPressed: _openExternally,
              icon: const Icon(Icons.open_in_new),
              tooltip: 'Open externally',
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

  Future<void> _openExternally() async {
    final current = source;
    if (current == null) return;
    final profile = widget.preferences.externalEditors.resolve(
      current.location,
    );
    if (profile == null) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('No external editor matches this source.'),
          action: SnackBarAction(label: 'Settings', onPressed: _showSettings),
        ),
      );
      return;
    }
    try {
      await const ExternalEditorLauncher().launch(profile, current.location);
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Opened in ${profile.name}.')));
      }
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Could not open ${profile.name}: $error'),
          action: SnackBarAction(label: 'Settings', onPressed: _showSettings),
        ),
      );
    }
  }
}
