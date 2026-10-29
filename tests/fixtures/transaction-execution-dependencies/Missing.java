package fixture;
public class Missing {
    abstract static class Nested { abstract void work(); }
    Nested receiver;
    public void run() { receiver.work(); }
}
