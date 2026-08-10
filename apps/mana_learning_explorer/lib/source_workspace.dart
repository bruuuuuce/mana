import 'dart:io';

/// Immutable, version-aware identity for a range used as Journey evidence.
class SourceLocation {
  const SourceLocation({
    required this.projectRoot,
    required this.path,
    required this.startLine,
    required this.endLine,
    this.revision,
    this.contentHash,
  });

  final String projectRoot;
  final String path;
  final int startLine;
  final int endLine;
  final String? revision;
  final String? contentHash;

  factory SourceLocation.fromAnchor(
    String projectRoot,
    Map<String, dynamic> anchor,
  ) {
    final range = anchor['range'] as Map<String, dynamic>? ?? const {};
    return SourceLocation(
      projectRoot: projectRoot,
      path: anchor['path'] as String? ?? '',
      startLine: range['start_line'] as int? ?? 1,
      endLine: range['end_line'] as int? ?? 1,
      revision: anchor['revision'] as String?,
      contentHash:
          anchor['content_hash'] as String? ??
          anchor['structural_fingerprint'] as String?,
    );
  }

  bool get isSafe =>
      path.isNotEmpty &&
      !path.startsWith('/') &&
      !path.split('/').any((part) => part == '..' || part.isEmpty);
  String get reference => '$path:$startLine-$endLine';
}

enum SourceState { snapshot, workingTree, snapshotUnavailable, missing }

class ResolvedSource {
  const ResolvedSource({
    required this.location,
    required this.state,
    this.contents,
    this.drifted = false,
  });

  final SourceLocation location;
  final SourceState state;
  final String? contents;
  final bool drifted;

  bool get available => contents != null;
  String get status => switch (state) {
    SourceState.snapshot =>
      drifted
          ? 'Analyzed snapshot — working tree differs'
          : 'Analyzed snapshot',
    SourceState.workingTree => 'Working-tree source (no snapshot identity)',
    SourceState.snapshotUnavailable =>
      'Analyzed snapshot unavailable — working tree is not authoritative',
    SourceState.missing => 'Source unavailable',
  };
}

class SourceResolver {
  Future<ResolvedSource> resolve(SourceLocation location) async {
    if (!location.isSafe) {
      return ResolvedSource(location: location, state: SourceState.missing);
    }
    final workingTree = File('${location.projectRoot}/${location.path}');
    final current = await workingTree.exists()
        ? await workingTree.readAsString()
        : null;
    final revision = location.revision;
    if (revision == null || revision.isEmpty) {
      return ResolvedSource(
        location: location,
        state: current == null ? SourceState.missing : SourceState.workingTree,
        contents: current,
      );
    }

    final snapshot = await Process.run('git', [
      '-C',
      location.projectRoot,
      'show',
      '$revision:${location.path}',
    ]);
    if (snapshot.exitCode == 0) {
      final contents = snapshot.stdout as String;
      return ResolvedSource(
        location: location,
        state: SourceState.snapshot,
        contents: contents,
        drifted: current != null && current != contents,
      );
    }
    return ResolvedSource(
      location: location,
      state: current == null
          ? SourceState.missing
          : SourceState.snapshotUnavailable,
      contents: current,
    );
  }
}

String sourceLanguage(String path) {
  final extension = path.split('.').last.toLowerCase();
  return switch (extension) {
    'dart' => 'dart',
    'java' => 'java',
    'kt' || 'kts' => 'kotlin',
    'js' || 'jsx' => 'javascript',
    'ts' || 'tsx' => 'typescript',
    'py' => 'python',
    'sh' || 'bash' || 'zsh' => 'bash',
    'json' => 'json',
    'yaml' || 'yml' => 'yaml',
    'sql' => 'sql',
    'swift' => 'swift',
    _ => 'plaintext',
  };
}
