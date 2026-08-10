import 'package:flutter_test/flutter_test.dart';
import 'package:mana_learning_explorer/external_editor.dart';
import 'package:mana_learning_explorer/source_workspace.dart';

void main() {
  const vscode = ExternalEditorProfile(
    id: 'vscode',
    name: 'VS Code',
    executable: 'code',
    arguments: ['--goto', '{file}:{line}:{column}'],
  );
  const idea = ExternalEditorProfile(
    id: 'idea',
    name: 'IntelliJ',
    executable: 'idea',
    arguments: ['--line', '{line}', '{file}'],
  );
  const location = SourceLocation(
    projectRoot: '/project with spaces',
    path: 'lib/sample.dart',
    startLine: 27,
    endLine: 31,
  );

  test('resolves mappings by path, extension, language, then fallback', () {
    const settings = ExternalEditorSettings(
      profiles: [vscode, idea],
      defaultProfileId: 'vscode',
      extensionProfiles: {'dart': 'idea'},
      languageProfiles: {'python': 'idea'},
      pathOverrides: [
        EditorPathOverride(pathPrefix: 'lib/', profileId: 'vscode'),
      ],
    );
    expect(settings.resolve(location), vscode); // path overrides extension
    expect(settings.resolve(location.copyWithPath('test.dart')), idea);
    expect(settings.resolve(location.copyWithPath('tool/script.py')), idea);
    expect(settings.resolve(location.copyWithPath('README')), vscode);
  });

  test('builds structured invocation without shell concatenation', () {
    final invocation = const ExternalEditorLauncher().buildInvocation(
      vscode,
      location,
    );
    expect(invocation.executable, 'code');
    expect(invocation.arguments, [
      '--goto',
      '/project with spaces/lib/sample.dart:27:1',
    ]);
  });

  test(
    'accepts explicit URI profiles without converting them to a shell command',
    () {
      const profile = ExternalEditorProfile(
        id: 'uri',
        name: 'URI editor',
        uriTemplate: 'editor://open?line={line}',
      );
      final invocation = const ExternalEditorLauncher().buildInvocation(
        profile,
        location,
      );
      expect(invocation.usesUri, isTrue);
      expect(invocation.uri?.scheme, 'editor');
      expect(invocation.uri?.queryParameters['line'], '27');
    },
  );

  test('round-trips persisted profile and mappings', () {
    const settings = ExternalEditorSettings(
      profiles: [vscode],
      defaultProfileId: 'vscode',
      extensionProfiles: {'dart': 'vscode'},
    );
    final decoded = ExternalEditorSettings.fromJson(settings.toJson());
    expect(decoded.resolve(location)?.name, 'VS Code');
  });
}

extension on SourceLocation {
  SourceLocation copyWithPath(String path) => SourceLocation(
    projectRoot: projectRoot,
    path: path,
    startLine: startLine,
    endLine: endLine,
    revision: revision,
    contentHash: contentHash,
  );
}
