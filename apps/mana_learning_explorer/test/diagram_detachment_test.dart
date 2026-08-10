import 'package:flutter_test/flutter_test.dart';
import 'package:mana_learning_explorer/diagram_detachment.dart';

void main() {
  test('unavailable detachment leaves the shared presentation attached', () {
    final state = DiagramWindowState();
    addTearDown(state.dispose);

    expect(
      state.requestDetach(DiagramDetachmentCapability.unavailable),
      isFalse,
    );
    expect(state.value, isFalse);

    state.attach();
    expect(state.value, isFalse);
  });
}
