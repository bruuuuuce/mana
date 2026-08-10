package example;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PaymentController {
  private final PaymentService paymentService;

  public PaymentController(PaymentService paymentService) {
    this.paymentService = paymentService;
  }

  @PostMapping("/payments")
  public String createPayment() {
    return paymentService.authorize();
  }

  @PostMapping("/unrelated")
  public String unrelated() {
    return "not part of the requested Journey";
  }
}
