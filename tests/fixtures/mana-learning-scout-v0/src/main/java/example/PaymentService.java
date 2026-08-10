package example;

import org.springframework.transaction.annotation.Transactional;

public class PaymentService {
  private final PaymentRepository paymentRepository;

  public PaymentService(PaymentRepository paymentRepository) {
    this.paymentRepository = paymentRepository;
  }

  @Transactional
  public String authorize() {
    paymentRepository.save();
    return "accepted";
  }

  public void unrelatedWork() {
    paymentRepository.deleteAll();
  }
}
