import 'dart:io';

import 'source_workspace.dart';

/// A configured external editor. Argument templates are expanded into distinct
/// Process arguments; they are never passed through a shell.
class ExternalEditorProfile {
  const ExternalEditorProfile({
    required this.id,
    required this.name,
    this.executable,
    this.arguments = const ['{file}'],
    this.uriTemplate,
  });

  final String id;
  final String name;
  final String? executable;
  final List<String> arguments;
  final String? uriTemplate;

  bool get isUriProfile => uriTemplate != null && uriTemplate!.isNotEmpty;
  bool get isValid =>
      id.trim().isNotEmpty &&
      name.trim().isNotEmpty &&
      (isUriProfile || (executable != null && executable!.trim().isNotEmpty));

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    if (executable != null) 'executable': executable,
    'arguments': arguments,
    if (uriTemplate != null) 'uriTemplate': uriTemplate,
  };

  factory ExternalEditorProfile.fromJson(Map<String, dynamic> json) =>
      ExternalEditorProfile(
        id: json['id'] as String? ?? '',
        name: json['name'] as String? ?? '',
        executable: json['executable'] as String?,
        arguments:
            (json['arguments'] as List?)?.whereType<String>().toList() ??
            const ['{file}'],
        uriTemplate: json['uriTemplate'] as String?,
      );
}

class EditorPathOverride {
  const EditorPathOverride({required this.pathPrefix, required this.profileId});
  final String pathPrefix;
  final String profileId;
  Map<String, dynamic> toJson() => {
    'pathPrefix': pathPrefix,
    'profileId': profileId,
  };
  factory EditorPathOverride.fromJson(Map<String, dynamic> json) =>
      EditorPathOverride(
        pathPrefix: json['pathPrefix'] as String? ?? '',
        profileId: json['profileId'] as String? ?? '',
      );
}

/// Project-scoped editor choices. Resolution is deliberately deterministic:
/// longest matching path prefix, extension, detected language, then default.
class ExternalEditorSettings {
  const ExternalEditorSettings({
    this.profiles = const [],
    this.defaultProfileId,
    this.extensionProfiles = const {},
    this.languageProfiles = const {},
    this.pathOverrides = const [],
  });
  final List<ExternalEditorProfile> profiles;
  final String? defaultProfileId;
  final Map<String, String> extensionProfiles;
  final Map<String, String> languageProfiles;
  final List<EditorPathOverride> pathOverrides;

  ExternalEditorProfile? resolve(SourceLocation location) {
    final profileById = {for (final profile in profiles) profile.id: profile};
    final normalizedPath = location.path.replaceAll('\\', '/').toLowerCase();
    final overrides =
        pathOverrides.where((override) {
            final prefix = override.pathPrefix
                .replaceAll('\\', '/')
                .toLowerCase();
            return prefix.isNotEmpty && normalizedPath.startsWith(prefix);
          }).toList()
          ..sort((a, b) => b.pathPrefix.length.compareTo(a.pathPrefix.length));
    final extension = _extension(location.path);
    final language = sourceLanguage(location.path);
    final id = overrides.isNotEmpty
        ? overrides.first.profileId
        : extensionProfiles[extension] ??
              languageProfiles[language] ??
              defaultProfileId;
    final profile = id == null ? null : profileById[id];
    return profile?.isValid == true ? profile : null;
  }

  Map<String, dynamic> toJson() => {
    'profiles': profiles.map((profile) => profile.toJson()).toList(),
    'defaultProfileId': defaultProfileId,
    'extensionProfiles': extensionProfiles,
    'languageProfiles': languageProfiles,
    'pathOverrides': pathOverrides
        .map((override) => override.toJson())
        .toList(),
  };

  factory ExternalEditorSettings.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const ExternalEditorSettings();
    Map<String, String> mapping(String key) =>
        (json[key] as Map?)?.map(
          (k, v) => MapEntry('$k'.toLowerCase(), '$v'),
        ) ??
        const {};
    return ExternalEditorSettings(
      profiles:
          (json['profiles'] as List?)
              ?.whereType<Map>()
              .map(
                (item) => ExternalEditorProfile.fromJson(
                  item.cast<String, dynamic>(),
                ),
              )
              .toList() ??
          const [],
      defaultProfileId: json['defaultProfileId'] as String?,
      extensionProfiles: mapping('extensionProfiles'),
      languageProfiles: mapping('languageProfiles'),
      pathOverrides:
          (json['pathOverrides'] as List?)
              ?.whereType<Map>()
              .map(
                (item) =>
                    EditorPathOverride.fromJson(item.cast<String, dynamic>()),
              )
              .toList() ??
          const [],
    );
  }

  static String _extension(String path) {
    final file = path.split('/').last;
    final index = file.lastIndexOf('.');
    return index < 0 ? '' : file.substring(index + 1).toLowerCase();
  }
}

class ExternalEditorInvocation {
  const ExternalEditorInvocation.executable(this.executable, this.arguments)
    : uri = null;
  const ExternalEditorInvocation.uri(this.uri)
    : executable = null,
      arguments = const [];
  final String? executable;
  final List<String> arguments;
  final Uri? uri;
  bool get usesUri => uri != null;
}

class ExternalEditorLauncher {
  const ExternalEditorLauncher();

  ExternalEditorInvocation buildInvocation(
    ExternalEditorProfile profile,
    SourceLocation location,
  ) {
    final values = {
      'file':
          '${location.projectRoot}${Platform.pathSeparator}${location.path}',
      'path': location.path,
      'line': '${location.startLine}',
      'column': '1',
      'projectRoot': location.projectRoot,
    };
    String expand(String value) => value.replaceAllMapped(
      RegExp(r'\{(file|path|line|column|projectRoot)\}'),
      (match) => values[match.group(1)]!,
    );
    if (profile.isUriProfile) {
      final parsed = Uri.tryParse(expand(profile.uriTemplate!));
      if (parsed == null || !parsed.hasScheme) {
        throw ArgumentError('The editor URI is not valid.');
      }
      return ExternalEditorInvocation.uri(parsed);
    }
    return ExternalEditorInvocation.executable(
      profile.executable!,
      profile.arguments.map(expand).toList(),
    );
  }

  Future<void> launch(
    ExternalEditorProfile profile,
    SourceLocation location,
  ) async {
    final invocation = buildInvocation(profile, location);
    if (invocation.usesUri) {
      final result = await Process.run('open', [invocation.uri.toString()]);
      if (result.exitCode != 0) {
        throw StateError(result.stderr.toString().trim());
      }
      return;
    }
    try {
      await Process.start(invocation.executable!, invocation.arguments);
    } on ProcessException catch (error) {
      throw StateError('Could not start ${profile.name}: ${error.message}');
    }
  }

  Future<void> test(ExternalEditorProfile profile, String projectRoot) =>
      launch(
        profile,
        SourceLocation(
          projectRoot: projectRoot,
          path: '.mana-editor-profile-test',
          startLine: 1,
          endLine: 1,
        ),
      );
}
