import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:mana_learning_explorer/source_workspace.dart';

void main() {
  test(
    'resolves the analyzed snapshot and reports working-tree drift',
    () async {
      final root = await Directory.systemTemp.createTemp('mana-source-');
      addTearDown(() => root.delete(recursive: true));
      await _git(root.path, ['init']);
      await _git(root.path, ['config', 'user.email', 'test@mana.local']);
      await _git(root.path, ['config', 'user.name', 'Mana test']);
      final source = File('${root.path}/lib/example.dart');
      await source.parent.create(recursive: true);
      await source.writeAsString('void main() {}\n');
      await _git(root.path, ['add', '.']);
      await _git(root.path, ['commit', '-m', 'snapshot']);
      final revision = (await _git(root.path, ['rev-parse', 'HEAD'])).trim();
      await source.writeAsString('void main() { print("drift"); }\n');

      final resolved = await SourceResolver().resolve(
        SourceLocation(
          projectRoot: root.path,
          path: 'lib/example.dart',
          startLine: 1,
          endLine: 1,
          revision: revision,
        ),
      );

      expect(resolved.state, SourceState.snapshot);
      expect(resolved.contents, 'void main() {}\n');
      expect(resolved.drifted, isTrue);
    },
  );

  test(
    'does not treat a current file as authoritative when its snapshot is absent',
    () async {
      final root = await Directory.systemTemp.createTemp(
        'mana-source-missing-',
      );
      addTearDown(() => root.delete(recursive: true));
      final source = File('${root.path}/source.java');
      await source.writeAsString('class Source {}\n');

      final resolved = await SourceResolver().resolve(
        SourceLocation(
          projectRoot: root.path,
          path: 'source.java',
          startLine: 1,
          endLine: 1,
          revision: 'does-not-exist',
        ),
      );

      expect(resolved.state, SourceState.snapshotUnavailable);
      expect(resolved.available, isTrue);
      expect(resolved.status, contains('not authoritative'));
    },
  );

  test('resolves supported source languages and rejects unsafe locations', () {
    expect(sourceLanguage('lib/page.dart'), 'dart');
    expect(sourceLanguage('scripts/check.sh'), 'bash');
    expect(sourceLanguage('notes.unknown'), 'plaintext');
    expect(
      SourceLocation(
        projectRoot: '/project',
        path: '../outside.dart',
        startLine: 1,
        endLine: 1,
      ).isSafe,
      isFalse,
    );
  });

  test('reports a missing source explicitly', () async {
    final root = await Directory.systemTemp.createTemp('mana-source-absent-');
    addTearDown(() => root.delete(recursive: true));

    final resolved = await SourceResolver().resolve(
      SourceLocation(
        projectRoot: root.path,
        path: 'missing.dart',
        startLine: 1,
        endLine: 2,
      ),
    );

    expect(resolved.state, SourceState.missing);
    expect(resolved.available, isFalse);
  });
}

Future<String> _git(String root, List<String> arguments) async {
  final result = await Process.run('git', ['-C', root, ...arguments]);
  if (result.exitCode != 0) throw StateError(result.stderr.toString());
  return result.stdout.toString();
}
