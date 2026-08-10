package example;

public final class ProviderRouter {
  private final PaymentProvider provider;

  public ProviderRouter(PaymentProvider provider) {
    this.provider = provider;
  }

  public void authorize() {
    provider.authorize();
  }

  interface PaymentProvider {
    void authorize();
  }
}
