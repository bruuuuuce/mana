import 'package:flutter/foundation.dart';

/// A future native window must consume the same route notifier and emit intents
/// through the existing route controller. This build deliberately exposes no
/// detach operation until that shared-session bridge exists.
class DiagramDetachmentCapability {
  const DiagramDetachmentCapability._({required this.reason});

  final String reason;
  bool get isSupported => false;

  static const unavailable = DiagramDetachmentCapability._(
    reason:
        'A synchronized native secondary-window bridge is not installed in this build. The Diagram Workspace remains in the application window.',
  );
}

class DiagramWindowState extends ValueNotifier<bool> {
  DiagramWindowState() : super(false);

  /// Never changes traversal state; attach/detach only changes presentation.
  bool requestDetach(DiagramDetachmentCapability capability) {
    if (!capability.isSupported) return false;
    value = true;
    return true;
  }

  void attach() => value = false;
}
