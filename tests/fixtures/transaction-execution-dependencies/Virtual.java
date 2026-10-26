package fixture;
public class Virtual {
    static class Nested { void work() {} }
    Nested receiver;
    public void run() { receiver.work(); }
}
