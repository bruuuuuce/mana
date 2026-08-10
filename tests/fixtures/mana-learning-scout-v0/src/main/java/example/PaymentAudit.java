package example;

import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class PaymentAudit {
  @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
  public void recordAuditEntry() {
  }
}
